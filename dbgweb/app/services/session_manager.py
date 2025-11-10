"""Session management for dbgweb."""
from __future__ import annotations

import asyncio
import uuid
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.utils.io import strip_ansi
from dbgcopilot.backends.gdb_subprocess import GdbSubprocessBackend
from dbgcopilot.backends.lldb_inprocess import LldbInProcessBackend
from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend
from dbgcopilot.backends.lldb_api import LldbApiBackend


logger = logging.getLogger(__name__)


def _queue_factory() -> asyncio.Queue[str]:
    return asyncio.Queue()


@dataclass
class Session:
    session_id: str
    orchestrator: CopilotOrchestrator
    state: SessionState
    debugger_backend: Any
    debugger_queue: asyncio.Queue[str] = field(default_factory=_queue_factory)
    chat_queue: asyncio.Queue[str] = field(default_factory=_queue_factory)


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        debugger: str,
        provider: str,
        model: Optional[str],
        api_key: Optional[str],
        program: Optional[str],
        corefile: Optional[str],
        auto_approve: bool = False,
    ) -> tuple[Session, list[str]]:
        async with self._lock:
            session_id = uuid.uuid4().hex[:8]
            backend = self._create_backend(debugger, program=program, corefile=corefile)
            state = SessionState(session_id=session_id)
            state.provider_name = provider
            state.model_override = model
            state.provider_api_key = api_key
            state.selected_provider = provider
            state.config["llm_provider"] = provider
            if api_key:
                state.config[f"{provider.replace('-', '_')}_api_key"] = api_key
            if model:
                state.config[f"{provider.replace('-', '_')}_model"] = model
            if auto_approve:
                state.auto_accept_commands = True
                state.config["auto_accept_commands"] = "true"
            backend_name = getattr(backend, "name", "")
            if program and backend_name in {"delve", "radare2"}:
                state.config["program"] = program
            orchestrator = CopilotOrchestrator(backend, state)
            session = Session(
                session_id=session_id,
                orchestrator=orchestrator,
                state=state,
                debugger_backend=backend,
            )
            loop = asyncio.get_running_loop()

            def emit_debugger_output(text: str) -> None:
                if not text:
                    return
                formatted = self._format_debugger_output(session, text)
                if not formatted:
                    return
                asyncio.run_coroutine_threadsafe(session.debugger_queue.put(formatted), loop)

            state.debugger_output_sink = emit_debugger_output

            def emit_chat(text: str) -> None:
                if not text:
                    return
                asyncio.run_coroutine_threadsafe(
                    session.chat_queue.put(strip_ansi(text)),
                    loop,
                )

            state.chat_output_sink = emit_chat
            self.sessions[session_id] = session
            initial_messages: list[str] = []
            if program:
                init_output = await asyncio.to_thread(self._load_program_for_backend, session, program)
                if init_output:
                    formatted = self._format_debugger_output(session, init_output)
                    if formatted:
                        initial_messages.append(formatted)
                        await session.debugger_queue.put(formatted)
            if corefile:
                init_output = await asyncio.to_thread(self._load_corefile_for_backend, session, corefile)
                if init_output:
                    formatted = self._format_debugger_output(session, init_output)
                    if formatted:
                        initial_messages.append(formatted)
                        await session.debugger_queue.put(formatted)
            if not program and not corefile:
                prompt = self._prompt_text(session)
                if prompt:
                    initial_messages.append(prompt)
                    await session.debugger_queue.put(prompt)
            return session, initial_messages

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            session = self.sessions.pop(session_id, None)
            if session and hasattr(session.debugger_backend, "close"):
                try:
                    session.debugger_backend.close()
                except Exception:
                    pass

    def set_auto_approve(self, session: Session, enabled: bool) -> None:
        session.state.auto_accept_commands = enabled
        if enabled:
            session.state.config["auto_accept_commands"] = "true"
        else:
            session.state.config.pop("auto_accept_commands", None)

    async def run_debugger_command(self, session: Session, command: str) -> None:
        result = await asyncio.to_thread(session.debugger_backend.run_command, command)
        formatted = self._format_debugger_output(session, result)
        if formatted:
            await session.debugger_queue.put(formatted)
        session.state.last_output = result or ""
        session.state.attempts.append(
            Attempt(cmd=command, output_snippet=(result or "")[:160])
        )

    async def run_chat(self, session: Session, message: str) -> str:
        def _ask() -> str:
            return session.orchestrator.ask(message)

        answer = await asyncio.to_thread(_ask)
        clean_answer = strip_ansi(answer)
        if (
            clean_answer
            and not session.state.last_answer_streamed
            and not session.state.pending_chat_events
        ):
            await session.chat_queue.put(clean_answer)
        pending_chat = list(session.state.pending_chat)
        session.state.pending_chat.clear()
        for chunk in pending_chat:
            cleaned = strip_ansi(chunk)
            if cleaned:
                await session.chat_queue.put(cleaned)
        pending_events = list(session.state.pending_chat_events)
        session.state.pending_chat_events.clear()
        for event in pending_events:
            try:
                payload = json.dumps(event)
            except TypeError:
                continue
            await session.chat_queue.put(payload)
        pending = list(session.state.pending_outputs)
        session.state.pending_outputs.clear()
        if pending:
            for chunk in pending:
                formatted = self._format_debugger_output(session, chunk)
                if formatted:
                    await session.debugger_queue.put(formatted)
        elif session.state.last_output and not getattr(session.state, "debugger_output_sink", None):
            formatted = self._format_debugger_output(session, session.state.last_output)
            if formatted:
                await session.debugger_queue.put(formatted)
        return clean_answer

    def _create_backend(self, debugger: str, program: Optional[str], corefile: Optional[str]):
        if debugger == "gdb":
            backend = GdbSubprocessBackend()
            backend.initialize_session()
            return backend
        if debugger == "lldb":
            return self._create_lldb_backend()
        if debugger == "delve":
            if not program:
                raise ValueError("Delve requires a binary path. Provide one via the program field.")
            from dbgcopilot.backends.delve_subprocess import DelveSubprocessBackend

            backend = DelveSubprocessBackend(program=program)
            backend.initialize_session()
            return backend
        if debugger == "radare2":
            if not program:
                raise ValueError("Radare2 requires a binary path. Provide one via the program field.")
            from dbgcopilot.backends.radare2_subprocess import Radare2SubprocessBackend

            backend = Radare2SubprocessBackend(program=program)
            backend.initialize_session()
            return backend
        raise ValueError(f"Unsupported debugger: {debugger}")

    def _create_lldb_backend(self):
        api_error: Optional[Exception] = None
        try:
            backend = LldbApiBackend()
            backend.initialize_session()
            return backend
        except Exception as exc:  # pragma: no cover - depends on environment
            api_error = exc

        try:
            import lldb  # type: ignore

            if getattr(lldb, "debugger", None):
                backend = LldbInProcessBackend()
                backend.initialize_session()
                return backend
        except Exception:
            pass

        backend = LldbSubprocessBackend()
        backend.initialize_session()
        if api_error:
            logger.warning("LLDB API backend unavailable, using subprocess backend: %s", api_error)
        return backend

    def _load_program_for_backend(self, session: Session, program: str) -> Optional[str]:
        backend = session.debugger_backend
        name = getattr(backend, "name", "").lower()
        if name == "gdb":
            return backend.run_command(f"file {program}")
        if name == "lldb":
            return backend.run_command(f"file {program}")
        if name == "delve":
            return getattr(backend, "startup_output", "")
        if name == "radare2":
            return getattr(backend, "startup_output", "")
        return None

    def _load_corefile_for_backend(self, session: Session, corefile: str) -> Optional[str]:
        backend = session.debugger_backend
        name = getattr(backend, "name", "").lower()
        if name == "gdb":
            return backend.run_command(f"core-file {corefile}")
        if name == "lldb":
            return backend.run_command(f"target create -c {corefile}")
        return None

    def _prompt_text(self, session: Session) -> str:
        prompt = getattr(session.debugger_backend, "prompt", "") or ""
        prompt = prompt.replace("\r", "").replace("\n", "")
        if prompt and not prompt.endswith(" "):
            prompt = f"{prompt} "
        return prompt

    def _format_debugger_output(self, session: Session, text: Optional[str]) -> str:
        raw = (text or "").rstrip("\r")
        if raw:
            raw = (
                raw.replace("\x1b[?2004l", "")
                .replace("\x1b[?2004h", "")
                .replace("\u001b[?2004l", "")
                .replace("\u001b[?2004h", "")
            )
        backend_name = getattr(session.debugger_backend, "name", "").lower()
        if raw:
            lines = raw.splitlines()
            if lines:
                first = lines[0]
                prompt_variants: list[str] = []
                backend_prompt = getattr(session.debugger_backend, "prompt", "") or ""
                if backend_prompt:
                    prompt_variants.append(strip_ansi(backend_prompt).strip().lower())
                prompt_variants.extend(["(gdb)", "gdb>", "(lldb)", "lldb>"])
                ansi_prefix = r"(?:\x1b\[[0-9;]*m)*"
                prompt_patterns: list[re.Pattern[str]] = []
                for prefix in prompt_variants:
                    if not prefix:
                        continue
                    prompt_patterns.append(
                        re.compile(rf"^{ansi_prefix}{re.escape(prefix)}\s*", re.IGNORECASE)
                    )
                for pattern in prompt_patterns:
                    match = pattern.match(first)
                    if not match:
                        continue
                    remainder = first[match.end():].lstrip()
                    if remainder:
                        lines[0] = remainder
                    else:
                        lines = lines[1:]
                    break
            if backend_name == "delve" and lines:
                prompt_token = re.compile(r"^(?:\x1b\[[0-9;]*m)*(?:delve>|dlv>)\s*", re.IGNORECASE)
                cleaned: list[str] = []
                for line in lines:
                    if not line:
                        cleaned.append(line)
                        continue
                    if line.startswith("(dlv)"):
                        suffix = line[len("(dlv)") :]
                        suffix = suffix.lstrip()
                        suffix = prompt_token.sub("", suffix).lstrip()
                        cleaned.append("(dlv)" + (f" {suffix}" if suffix else ""))
                        continue
                    cleaned_line = prompt_token.sub("", line)
                    cleaned.append(cleaned_line)
                lines = cleaned
            raw = "\n".join(lines)
        prompt = self._prompt_text(session)
        if prompt:
            if raw:
                if not raw.endswith("\n"):
                    raw += "\n"
                raw += prompt
            else:
                raw = prompt
        return raw


session_manager = SessionManager()

"""Session management for dbgweb."""
from __future__ import annotations

import asyncio
import uuid
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.utils.io import strip_ansi
from dbgcopilot.backends.gdb_subprocess import GdbSubprocessBackend
from dbgcopilot.backends.lldb_inprocess import LldbInProcessBackend
from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend


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
    ) -> tuple[Session, list[str]]:
        async with self._lock:
            session_id = uuid.uuid4().hex[:8]
            backend = self._create_backend(debugger)
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
                init_output = await asyncio.to_thread(backend.run_command, f"file {program}")
                formatted = self._format_debugger_output(session, init_output)
                if formatted:
                    initial_messages.append(formatted)
                    await session.debugger_queue.put(formatted)
            if corefile:
                init_output = await asyncio.to_thread(backend.run_command, f"core-file {corefile}")
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

    def _create_backend(self, debugger: str):
        if debugger == "gdb":
            backend = GdbSubprocessBackend()
        elif debugger == "lldb":
            try:
                import lldb  # type: ignore

                backend = LldbInProcessBackend()
            except Exception:
                backend = LldbSubprocessBackend()
        else:
            raise ValueError(f"Unsupported debugger: {debugger}")
        backend.initialize_session()
        return backend

    def _prompt_text(self, session: Session) -> str:
        prompt = getattr(session.debugger_backend, "prompt", "") or ""
        prompt = prompt.replace("\r", "").replace("\n", "")
        if prompt and not prompt.endswith(" "):
            prompt = f"{prompt} "
        return prompt

    def _format_debugger_output(self, session: Session, text: Optional[str]) -> str:
        clean = strip_ansi((text or "").rstrip("\r"))
        if clean:
            lines = clean.splitlines()
            if lines:
                first = lines[0]
                lowered = first.lower()
                if lowered.startswith("gdb> "):
                    stripped = first[5:].lstrip()
                    if stripped:
                        lines[0] = stripped
                    else:
                        lines = lines[1:]
                elif lowered.startswith("lldb> "):
                    stripped = first[6:].lstrip()
                    if stripped:
                        lines[0] = stripped
                    else:
                        lines = lines[1:]
                clean = "\n".join(lines)
        prompt = self._prompt_text(session)
        if prompt:
            if clean:
                if not clean.endswith("\n"):
                    clean += "\n"
                clean += prompt
            else:
                clean = prompt
        return clean


session_manager = SessionManager()

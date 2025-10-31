"""Session management for dbgweb."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.utils.io import strip_ansi
from dbgcopilot.backends.gdb_subprocess import GdbSubprocessBackend
from dbgcopilot.backends.lldb_inprocess import LldbInProcessBackend
from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend


@dataclass
class Session:
    session_id: str
    orchestrator: CopilotOrchestrator
    state: SessionState
    debugger_backend: Any
    debugger_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    chat_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)


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
    ) -> Session:
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
            self.sessions[session_id] = session
            if program:
                init_output = await asyncio.to_thread(backend.run_command, f"file {program}")
                await session.debugger_queue.put(strip_ansi(init_output or ""))
            if corefile:
                init_output = await asyncio.to_thread(backend.run_command, f"core-file {corefile}")
                await session.debugger_queue.put(strip_ansi(init_output or ""))
            return session

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
        await session.debugger_queue.put(strip_ansi(result or ""))
        session.state.last_output = result or ""
        session.state.attempts.append(
            Attempt(cmd=command, output_snippet=(result or "")[:160])
        )

    async def run_chat(self, session: Session, message: str) -> str:
        def _ask() -> str:
            return session.orchestrator.ask(message)

        answer = await asyncio.to_thread(_ask)
        clean_answer = strip_ansi(answer)
        await session.chat_queue.put(clean_answer)
        # When orchestrator executes a command, last_output will reflect it. Forward to debugger queue.
        if session.state.last_output:
            await session.debugger_queue.put(strip_ansi(session.state.last_output))
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


session_manager = SessionManager()

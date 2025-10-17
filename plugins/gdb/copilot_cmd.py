"""GDB 'copilot' command scaffolding (POC).

Usage inside gdb:
  (gdb) source /abs/path/to/plugins/gdb/copilot_cmd.py
  (gdb) copilot new
  (gdb) copilot ask Why did it crash?

This file avoids heavy logic and defers to placeholders.
"""
from __future__ import annotations

import sys
import uuid


# Try to import gdb module (only available inside GDB)
try:
    import gdb  # type: ignore
except Exception:  # pragma: no cover
    gdb = None  # type: ignore


def _ensure_paths():  # pragma: no cover - depends on runtime
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_paths()

from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.core.orchestrator import AgentOrchestrator
from dbgcopilot.backends.gdb_inprocess import GdbInProcessBackend


SESSION: SessionState | None = None
ORCH: AgentOrchestrator | None = None
BACKEND = GdbInProcessBackend()


def _require_session() -> None:
    if SESSION is None:
        raise gdb.GdbError("No copilot session. Run 'copilot new' first.")


class CopilotNew(gdb.Command):  # type: ignore
    """Start a new copilot session and enter nested prompt (POC)."""

    def __init__(self) -> None:
        super().__init__("copilot new", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):  # pragma: no cover - gdb environment
        global SESSION, ORCH
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        ORCH = AgentOrchestrator(BACKEND, SESSION)
        BACKEND.initialize_session()
        gdb.write(f"[copilot] New session: {sid}\n")
        gdb.execute("python from dbgcopilot.plugins.gdb.repl import start_repl; start_repl()")


class CopilotAsk(gdb.Command):  # type: ignore
    """Ask a question to copilot (outside nested prompt)."""

    def __init__(self) -> None:
        super().__init__("copilot ask", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):  # pragma: no cover
        _require_session()
        resp = ORCH.ask(arg)
        gdb.write(resp + "\n")


class CopilotSummary(gdb.Command):  # type: ignore
    """Show a brief session summary."""

    def __init__(self) -> None:
        super().__init__("copilot summary", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):  # pragma: no cover
        _require_session()
        gdb.write(ORCH.summary() + "\n")


def register():  # pragma: no cover
    CopilotNew()
    CopilotAsk()
    CopilotSummary()


if gdb is not None:  # pragma: no cover
    register()

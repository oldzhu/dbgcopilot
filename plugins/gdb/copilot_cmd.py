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


def _ensure_session() -> None:
    """Ensure a session exists. Create one lazily if missing."""
    global SESSION, ORCH
    if SESSION is None:
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        ORCH = AgentOrchestrator(BACKEND, SESSION)
        BACKEND.initialize_session()
        if gdb is not None:
            gdb.write(f"[copilot] New session: {sid}\n")


class CopilotCmd(gdb.Command):  # type: ignore
    """Single `copilot` command to launch the copilot> prompt.

    Usage inside gdb:
      (gdb) copilot           # open copilot> prompt (creates session if needed)
      (gdb) copilot new       # create a new session and open prompt
    """

    def __init__(self) -> None:
        super().__init__("copilot", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):  # pragma: no cover - gdb environment
        global SESSION, ORCH
        args = (arg or "").strip()
        if args == "new":
            # force new session
            sid = str(uuid.uuid4())[:8]
            SESSION = SessionState(session_id=sid)
            ORCH = AgentOrchestrator(BACKEND, SESSION)
            BACKEND.initialize_session()
            gdb.write(f"[copilot] New session: {sid}\n")
        else:
            # ensure a session exists
            _ensure_session()

        # Start nested prompt directly
        try:
            from dbgcopilot.plugins.gdb.repl import start_repl
            start_repl()
        except Exception:
            # Fallback to executing via gdb if direct import fails
            gdb.execute("python from dbgcopilot.plugins.gdb.repl import start_repl; start_repl()")


def register():  # pragma: no cover
    CopilotCmd()


if gdb is not None:  # pragma: no cover
    register()

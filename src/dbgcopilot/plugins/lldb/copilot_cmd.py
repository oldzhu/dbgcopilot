"""LLDB 'copilot' command scaffolding (packaged).

Usage inside lldb:
  (lldb) command script import dbgcopilot.plugins.lldb.copilot_cmd
  (lldb) copilot
  (lldb) copilot new

This registers a 'copilot' command that launches a nested copilot> REPL.
"""
from __future__ import annotations

import sys
import uuid

try:  # pragma: no cover - only available inside lldb
    import lldb  # type: ignore
except Exception:  # pragma: no cover
    lldb = None  # type: ignore

from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.backends.lldb_inprocess import LldbInProcessBackend


# Globals for REPL/state access
SESSION = None  # type: ignore
ORCH = None  # type: ignore
BACKEND = LldbInProcessBackend()


def _ensure_session():  # pragma: no cover - lldb environment
    global SESSION, ORCH
    if SESSION is None:
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        ORCH = CopilotOrchestrator(BACKEND, SESSION)
        BACKEND.initialize_session()
        if lldb is not None:
            print(f"[copilot] New session: {sid}")
    else:
        ORCH = CopilotOrchestrator(BACKEND, SESSION)


def _copilot_cmd(debugger, command, exe_ctx, result, internal_dict):  # pragma: no cover
    args = (command or "").strip()
    global SESSION, ORCH
    if args == "new":
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        ORCH = CopilotOrchestrator(BACKEND, SESSION)
        BACKEND.initialize_session()
        print(f"[copilot] New session: {sid}")
    else:
        ORCH = CopilotOrchestrator(BACKEND, SESSION)
        _ensure_session()
    try:
        from dbgcopilot.plugins.lldb.repl import start_repl
        start_repl()
    except Exception as e:
        print(f"[copilot] Error launching REPL: {e}")


def __lldb_init_module(debugger, internal_dict):  # pragma: no cover
    # Register 'copilot' command
    debugger.HandleCommand(
        "command script add -f dbgcopilot.plugins.lldb.copilot_cmd._copilot_cmd copilot"
    )
    print("[copilot] 'copilot' command is ready. Type 'copilot' to start.")

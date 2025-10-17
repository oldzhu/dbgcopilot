"""Nested copilot> REPL for GDB (POC).

This is a minimal placeholder that simulates ask/exec flows without LLM.
"""
from __future__ import annotations

try:
    import gdb  # type: ignore
except Exception:  # pragma: no cover
    gdb = None  # type: ignore

from dbgcopilot.core.orchestrator import AgentOrchestrator
from dbgcopilot.core.state import SessionState, Attempt


def _ctx():  # pragma: no cover - gdb environment
    # Access global instances from copilot_cmd
    from .copilot_cmd import ORCH, SESSION, BACKEND
    return ORCH, SESSION, BACKEND


def start_repl():  # pragma: no cover - gdb environment
    ORCH, SESSION, BACKEND = _ctx()
    if ORCH is None or SESSION is None:
        gdb.write("[copilot] No active session.\n")
        return
    gdb.write("[copilot] Entering copilot> (type 'exit' to leave)\n")
    while True:
        try:
            line = gdb.prompt_hook("copilot> ") if hasattr(gdb, "prompt_hook") else input("copilot> ")
        except EOFError:
            break
        cmd = (line or "").strip()
        if cmd in ("exit", "quit"):
            gdb.write("[copilot] Exiting copilot>\n")
            break
        if cmd.startswith("ask "):
            q = cmd[4:]
            resp = ORCH.ask(q)
            gdb.write(resp + "\n")
        elif cmd.startswith("exec "):
            raw = cmd[5:]
            out = BACKEND.run_command(raw)
            SESSION.last_output = out
            SESSION.attempts.append(Attempt(cmd=raw, output_snippet=out[:160]))
            gdb.write(out + "\n")
        elif cmd.startswith("goal "):
            SESSION.goal = cmd[5:]
            gdb.write(f"[copilot] Goal set: {SESSION.goal}\n")
        elif cmd == "summary":
            gdb.write(ORCH.summary() + "\n")
        else:
            gdb.write("[copilot] Commands: ask <q>, exec <gdb-cmd>, goal <text>, summary, exit\n")

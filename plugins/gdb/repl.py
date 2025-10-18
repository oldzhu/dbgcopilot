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


def _print_help():
    lines = [
        "copilot> commands:",
        "  /help            Show this help",
        "  /new             Start a new copilot session",
        "  /summary         Show session summary",
        "  /config          Configure LLM backend/settings (placeholder)",
        "  /exec <cmd>      Run a gdb command and record output",
        "  /goal <text>     Set debugging goal",
        "  exit or quit     Leave copilot>",
        "Any other input is treated as a natural language question to the LLM.",
    ]
    return "\n".join(lines)


def start_repl():  # pragma: no cover - gdb environment
    ORCH, SESSION, BACKEND = _ctx()
    if ORCH is None or SESSION is None:
        gdb.write("[copilot] No active session.\n")
        return
    gdb.write("[copilot] Entering copilot> (type '/help' or 'exit' to leave)\n")
    while True:
        try:
            line = gdb.prompt_hook("copilot> ") if hasattr(gdb, "prompt_hook") else input("copilot> ")
        except EOFError:
            break
        cmd = (line or "").strip()
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            gdb.write("[copilot] Exiting copilot>\n")
            break
        # Slash commands
        if cmd.startswith("/"):
            parts = cmd.split(maxsplit=1)
            verb = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if verb in ("/help", "/h"):
                gdb.write(_print_help() + "\n")
            elif verb == "/new":
                # create new session
                from .copilot_cmd import SESSION as GLOBAL_SESSION, ORCH as GLOBAL_ORCH, BACKEND as GLOBAL_BACKEND
                sid = str(__import__("uuid").uuid4())[:8]
                new_s = SessionState(session_id=sid)
                # rebind globals in module (best-effort for POC)
                globals_mod = __import__("dbgcopilot.plugins.gdb.copilot_cmd", fromlist=["SESSION", "ORCH"])
                setattr(globals_mod, "SESSION", new_s)
                setattr(globals_mod, "ORCH", AgentOrchestrator(GLOBAL_BACKEND, new_s))
                GLOBAL_BACKEND.initialize_session()
                gdb.write(f"[copilot] New session: {sid}\n")
            elif verb == "/summary":
                gdb.write(ORCH.summary() + "\n")
            elif verb == "/config":
                # show config and selected provider
                gdb.write(f"[copilot] Config: {SESSION.config}\n")
                gdb.write(f"[copilot] Selected provider: {SESSION.selected_provider}\n")
            elif verb == "/llm":
                # subcommands: list | use <name>
                sub = arg.split(maxsplit=1) if arg else [""]
                action = sub[0]
                if action == "list":
                    from dbgcopilot.llm import providers as _prov
                    gdb.write("Available LLM providers:\n")
                    for p in _prov.list_providers():
                        gdb.write(f"- {p}\n")
                elif action == "use" and len(sub) > 1:
                    from dbgcopilot.llm import providers as _prov
                    name = sub[1]
                    if _prov.get_provider(name) is None:
                        gdb.write(f"[copilot] Unknown provider: {name}\n")
                    else:
                        SESSION.selected_provider = name
                        gdb.write(f"[copilot] Selected provider: {name}\n")
                else:
                    gdb.write("Usage: /llm list | /llm use <name>\n")
            elif verb == "/exec":
                if not arg:
                    gdb.write("[copilot] Usage: /exec <gdb-cmd>\n")
                else:
                    out = BACKEND.run_command(arg)
                    SESSION.last_output = out
                    SESSION.attempts.append(Attempt(cmd=arg, output_snippet=out[:160]))
                    gdb.write(out + "\n")
            elif verb == "/goal":
                SESSION.goal = arg
                gdb.write(f"[copilot] Goal set: {SESSION.goal}\n")
            else:
                gdb.write("[copilot] Unknown slash command. Try /help\n")
            continue

        # Natural language: forward to orchestrator.ask
        try:
            resp = ORCH.ask(cmd)
            # record last hint as a fact optionally
            SESSION.facts.append(f"Q: {cmd}")
            SESSION.facts.append(f"A: {resp.splitlines()[0] if resp else ''}")
            gdb.write(resp + "\n")
        except Exception as e:
            gdb.write(f"[copilot] Error: {e}\n")

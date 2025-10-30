"""Standalone copilot> REPL that can launch and control debuggers.

Phase 2a: supports selecting GDB via a subprocess backend. LLDB will be added next.
"""
from __future__ import annotations

import sys
import uuid
from typing import Optional

from dbgcopilot.core.orchestrator import AgentOrchestrator
from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.utils.io import color_text


# Globals for a simple REPL
SESSION: Optional[SessionState] = None
BACKEND = None
ORCH: Optional[AgentOrchestrator] = None


def _ensure_session() -> SessionState:
    global SESSION
    if SESSION is None:
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
    return SESSION


def _echo(line: str, colors: bool = True) -> None:
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _print_help() -> str:
    return "\n".join(
        [
            "copilot> commands:",
            "  /help                      Show this help",
            "  /use gdb                   Select GDB (subprocess backend)",
            "  /use lldb                  Select LLDB (Python API if available; else subprocess)",
            "  /colors on|off             Toggle colored output in REPL and debugger (LLDB/GDB)",
            "  /agent on|off              Toggle agent mode (auto analysis and final report)",
            "  /new                       Start a new copilot session",
            "  /chatlog                   Show chat transcript",
            "  /config                    Show current config",
            "  /prompts show|reload       Show or reload prompt config",
            "  /exec <cmd>                Run a debugger command (after /use)",
            "  /llm list                  List LLM providers",
            "  /llm use <name>            Select provider",
            "  /llm models [provider]     List models for provider (OpenRouter & OpenAI-compatible)",
            "  /llm model [provider] <m>  Set model for provider (OpenRouter & OpenAI-compatible)",
            "  /llm key <provider> <key>  Set API key for provider (OpenRouter & OpenAI-compatible)",
            "  exit or quit               Leave copilot>",
            "Any other input is sent to the LLM.",
        ]
    )


def _lldb_install_hint() -> str:
    """Return a one-liner hint to install the LLDB Python module for this OS."""
    try:
        import sys as _sys
        plat = _sys.platform
    except Exception:
        plat = ""
    if plat.startswith("linux"):
        return "Hint: install LLDB Python bindings: sudo apt install lldb python3-lldb"
    if plat == "darwin":
        return "Hint: install Xcode CLT, then: xcrun python3 -c 'import lldb' (or conda install -c conda-forge lldb)"
    if plat.startswith("win"):
        return "Hint: use Conda to install LLDB Python: conda install -c conda-forge lldb"
    return "Hint: install LLDB Python bindings (e.g., conda install -c conda-forge lldb)"


def _select_gdb() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    try:
        from dbgcopilot.backends.gdb_subprocess import GdbSubprocessBackend
    except Exception as e:
        return f"[copilot] Failed to load GDB subprocess backend: {e}"
    BACKEND = GdbSubprocessBackend()
    try:
        BACKEND.initialize_session()
    except Exception as e:
        BACKEND = None
        return f"[copilot] Failed to start gdb: {e}"
    ORCH = AgentOrchestrator(BACKEND, s)
    return "[copilot] Using GDB (subprocess backend)."


def _handle_llm(cmd: str) -> str:
    parts = cmd.split()
    action = parts[0] if parts else ""
    from dbgcopilot.llm import providers as _prov
    s = _ensure_session()
    sel = s.selected_provider
    if action == "list":
        lines = ["Available LLM providers:"] + [f"- {p}" for p in _prov.list_providers()]
        return "\n".join(lines)
    if action == "use" and len(parts) >= 2:
        name = parts[1]
        if _prov.get_provider(name) is None:
            return f"[copilot] Unknown provider: {name}"
        s.selected_provider = name
        return f"[copilot] Selected provider: {name}"
    if action == "models":
        provider = parts[1] if len(parts) >= 2 else (sel or "")
        if not provider:
            return "[copilot] No provider selected. Use /llm use <name> first or pass a provider."
        if provider == "openrouter":
            try:
                from dbgcopilot.llm import openrouter as _or
                models = _or.list_models(s.config)
                if not models:
                    return "[copilot] No models returned. You may need to set an API key."
                return "OpenRouter models:\n" + "\n".join(f"- {m}" for m in models)
            except Exception as e:
                return f"[copilot] Error listing models: {e}"
        if provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
            try:
                from dbgcopilot.llm import openai_compat as _oa
                models = _oa.list_models(s.config, name=provider)
                if not models:
                    return f"[copilot] No models returned from {provider}. Some providers do not support model listing via API; you can still set a model with /llm model."
                return f"{provider} models:\n" + "\n".join(f"- {m}" for m in models)
            except Exception as e:
                return f"[copilot] Error listing models for {provider}: {e}"
        return f"[copilot] Model listing not supported for provider: {provider}"
    if action == "model":
        if len(parts) == 2:
            provider = sel
            model = parts[1]
        elif len(parts) >= 3:
            provider = parts[1]
            model = " ".join(parts[2:])
        else:
            provider = None
            model = None
        if not provider or not model:
            return "Usage: /llm model [provider] <model>"
        if provider == "openrouter":
            s.config["openrouter_model"] = model
            return f"[copilot] OpenRouter model set to: {model}"
        if provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
            key = provider.replace("-", "_") + "_model"
            s.config[key] = model
            return f"[copilot] {provider} model set to: {model}"
        return f"[copilot] Setting model not supported for provider: {provider}"
    if action == "key" and len(parts) >= 3:
        provider = parts[1]
        api_key = " ".join(parts[2:]).strip()
        if provider == "openrouter":
            if api_key:
                s.config["openrouter_api_key"] = api_key
                return "[copilot] OpenRouter API key set for this session."
            return "[copilot] Missing API key."
        if provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
            if api_key:
                key = provider.replace("-", "_") + "_api_key"
                s.config[key] = api_key
                return f"[copilot] {provider} API key set for this session."
            return "[copilot] Missing API key."
        return f"[copilot] API key setting not supported for provider: {provider}"
    return (
        "Usage: /llm list | /llm use <name> | /llm models [provider] | "
        "/llm model [provider] <model> | /llm key <provider> <api_key>"
    )


def _select_lldb() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    # Prefer the LLDB Python API backend (robust capture) and fall back to the
    # subprocess backend only if the Python module isn't available.
    try:
        from dbgcopilot.backends.lldb_api import LldbApiBackend
        BACKEND = LldbApiBackend()
        BACKEND.initialize_session()
        ORCH = AgentOrchestrator(BACKEND, s)
        return "[copilot] Using LLDB (API backend)."
    except Exception as api_err:
        try:
            from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend
        except Exception as e:
            return (
                f"[copilot] Failed to load LLDB backends: API error: {api_err}; subprocess import error: {e}\n"
                + _lldb_install_hint()
            )
        BACKEND = LldbSubprocessBackend()
        try:
            BACKEND.initialize_session()
        except Exception as sub_err:
            BACKEND = None
            return (
                f"[copilot] Failed to start lldb (API error: {api_err}); subprocess error: {sub_err}\n"
                + _lldb_install_hint()
            )
        ORCH = AgentOrchestrator(BACKEND, s)
        return "[copilot] Using LLDB (subprocess backend; Python API unavailable).\n" + _lldb_install_hint()


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_session()
    _echo("[copilot] Standalone REPL. Type /help. Choose a debugger with /use <debugger> (gdb|lldb).")
    while True:
        try:
            line = input("copilot> ")
        except EOFError:
            _echo("[copilot] Exiting copilot>")
            return 0
        except KeyboardInterrupt:
            _echo("^C")
            continue
        cmd = (line or "").strip()
        if not cmd:
            continue
        if cmd in {"exit", "quit"}:
            _echo("[copilot] Exiting copilot>")
            return 0

        # Slash commands
        if cmd.startswith("/"):
            verb, *rest = cmd.split(maxsplit=1)
            arg = rest[0] if rest else ""
            if verb in {"/help", "/h"}:
                _echo(_print_help())
                continue
            if verb == "/use":
                choice = arg.strip().lower()
                if choice == "gdb":
                    _echo(_select_gdb())
                elif choice == "lldb":
                    _echo(_select_lldb())
                else:
                    _echo("[copilot] Supported: /use gdb | /use lldb")
                continue
            if verb == "/new":
                sid = str(uuid.uuid4())[:8]
                globals()["SESSION"] = SessionState(session_id=sid)
                if ORCH is not None and BACKEND is not None:
                    globals()["ORCH"] = AgentOrchestrator(BACKEND, globals()["SESSION"])  # reload prompts per session
                _echo(f"[copilot] New session: {sid}")
                continue
            
            if verb == "/chatlog":
                s = _ensure_session()
                if not s.chatlog:
                    _echo("[copilot] No chat yet.")
                else:
                    for line in s.chatlog[-200:]:
                        _echo(line)
                continue
            if verb == "/config":
                s = _ensure_session()
                _echo(f"[copilot] Config: {s.config}")
                _echo(f"[copilot] Selected provider: {s.selected_provider}")
                _echo(f"[copilot] Mode: {s.mode}")
                continue
            if verb == "/agent":
                choice = (arg or "").strip().lower()
                if choice not in {"on", "off"}:
                    _echo("Usage: /agent on|off")
                    continue
                s = _ensure_session()
                s.mode = "auto" if choice == "on" else "interactive"
                _echo(f"[copilot] Agent mode {'enabled' if choice=='on' else 'disabled'}.")
                continue
            if verb == "/prompts":
                if arg.strip().lower() == "show":
                    try:
                        if ORCH is None:
                            _echo("[copilot] No debugger selected.")
                        else:
                            cfg = ORCH.get_prompt_config()
                            import json as _json
                            src = cfg.get("_source", "defaults")
                            txt = _json.dumps(cfg, indent=2, ensure_ascii=False)
                            _echo(f"[copilot] Prompt source: {src}")
                            _echo(txt)
                    except Exception as e:
                        _echo(f"[copilot] Error showing prompts: {e}")
                elif arg.strip().lower() == "reload":
                    try:
                        if ORCH is None:
                            _echo("[copilot] No debugger selected.")
                        else:
                            _echo(ORCH.reload_prompts())
                    except Exception as e:
                        _echo(f"[copilot] Error reloading prompts: {e}")
                else:
                    _echo("Usage: /prompts show | /prompts reload")
                continue
            if verb == "/exec":
                if BACKEND is None:
                    _echo("[copilot] No debugger selected. Use /use gdb first.")
                elif not arg:
                    _echo("[copilot] Usage: /exec <cmd>")
                else:
                    label = getattr(BACKEND, "name", "debugger") or "debugger"
                    s = _ensure_session()
                    line = f"{label}> {arg}"
                    _echo(color_text(line, "cyan", bold=True, enable=True) if s.colors_enabled else line)
                    try:
                        out = BACKEND.run_command(arg)
                    except Exception as e:
                        out = f"[copilot] Error: {e}"
                    s.last_output = out
                    s.attempts.append(Attempt(cmd=arg, output_snippet=(out or "")[:160]))
                    if out:
                        _echo(out)
                continue
            if verb == "/colors":
                choice = (arg or "").strip().lower()
                if choice not in {"on", "off"}:
                    _echo("Usage: /colors on|off")
                    continue
                enable = choice == "on"
                s = _ensure_session()
                s.colors_enabled = enable
                # Try to toggle debugger-side coloring when possible
                if BACKEND is not None:
                    try:
                        name = (getattr(BACKEND, "name", "") or "").lower()
                        if name == "lldb":
                            BACKEND.run_command(f"settings set use-color {'true' if enable else 'false'}")
                        elif name == "gdb":
                            # GDB 8.3+ supports style colors; ignore errors on older builds
                            BACKEND.run_command(f"set style enabled {'on' if enable else 'off'}")
                    except Exception:
                        pass
                _echo(f"[copilot] Colors {'enabled' if enable else 'disabled'}.")
                continue
            
            if verb == "/llm":
                _echo(_handle_llm(arg))
                continue
            _echo("[copilot] Unknown slash command. Try /help")
            continue

        # Natural language → orchestrator
        if ORCH is None:
            _echo("[copilot] No debugger selected. Use /use gdb first.")
            continue
        try:
            resp = ORCH.ask(cmd)
            _echo(resp)
        except Exception as e:
            _echo(f"[copilot] Error: {e}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

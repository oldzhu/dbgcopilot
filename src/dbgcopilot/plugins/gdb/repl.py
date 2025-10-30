"""Nested copilot> REPL for GDB (packaged).

This REPL expects that `dbgcopilot.plugins.gdb.copilot_cmd` has initialized
global objects and provides the `copilot` command in GDB.
"""

try:
    import gdb  # type: ignore
except Exception:  # pragma: no cover
    gdb = None  # type: ignore

from dbgcopilot.core.orchestrator import AgentOrchestrator
from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.utils.io import color_text


def _ctx():  # pragma: no cover - gdb environment
    # Access global instances from copilot_cmd
    from .copilot_cmd import ORCH, SESSION, BACKEND
    return ORCH, SESSION, BACKEND


def _print_help():
    lines = [
        "copilot> commands:",
        "  /help            Show this help",
        "  /new             Start a new copilot session",
        "  /chatlog         Show chat Q/A transcript",
        "  /config          Show current config",
        "  /agent on|off    Toggle agent mode (auto analysis and final report)",
        "  /debuginfod [on|off]  Show or toggle debuginfod setting",
        "  /colors [on|off] Toggle colored output (default on)",
        "  /prompts show    Show current prompt config",
        "  /prompts reload  Reload prompts from configs/prompts.json",
        "  /exec <cmd>      Run a gdb command and record output",
        "  /llm list                List available LLM providers",
        "  /llm use <name>          Switch to a provider",
    "  /llm models [provider]   List models for provider (default: selected; OpenRouter & OpenAI-compatible)",
    "  /llm model [provider] <model>  Set the model for provider (default: selected; OpenRouter & OpenAI-compatible)",
    "  /llm key <provider> <api_key>  Set API key for provider (stored in-session; OpenRouter & OpenAI-compatible)",
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
            use_hook = hasattr(gdb, "prompt_hook") and callable(getattr(gdb, "prompt_hook", None))
            line = gdb.prompt_hook("copilot> ") if use_hook else input("copilot> ")
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
                import uuid as _uuid
                sid = str(_uuid.uuid4())[:8]
                new_s = SessionState(session_id=sid)
                globals_mod = __import__("dbgcopilot.plugins.gdb.copilot_cmd", fromlist=["SESSION", "ORCH"])
                setattr(globals_mod, "SESSION", new_s)
                setattr(globals_mod, "ORCH", AgentOrchestrator(GLOBAL_BACKEND, new_s))
                GLOBAL_BACKEND.initialize_session()
                gdb.write(f"[copilot] New session: {sid}\n")
            
            elif verb == "/chatlog":
                # Print entire transcript; keep it simple for now
                if not SESSION.chatlog:
                    gdb.write("[copilot] No chat yet.\n")
                else:
                    for line in SESSION.chatlog[-200:]:  # avoid flooding
                        gdb.write(line + "\n")
            elif verb == "/config":
                gdb.write(f"[copilot] Config: {SESSION.config}\n")
                gdb.write(f"[copilot] Selected provider: {SESSION.selected_provider}\n")
                gdb.write(f"[copilot] Mode: {SESSION.mode}\n")
            elif verb == "/agent":
                choice = (arg or "").strip().lower()
                if choice not in {"on", "off"}:
                    gdb.write("Usage: /agent on|off\n")
                else:
                    SESSION.mode = "auto" if choice == "on" else "interactive"
                    gdb.write(f"[copilot] Agent mode {'enabled' if choice=='on' else 'disabled'}.\n")
            elif verb == "/prompts":
                sub = arg.strip().lower()
                if sub == "show":
                    try:
                        cfg = ORCH.get_prompt_config()
                        import json as _json
                        src = cfg.get("_source", "defaults")
                        txt = _json.dumps(cfg, indent=2, ensure_ascii=False)
                        gdb.write(f"[copilot] Prompt source: {src}\n")
                        gdb.write(txt + "\n")
                    except Exception as e:
                        gdb.write(f"[copilot] Error showing prompts: {e}\n")
                elif sub == "reload":
                    try:
                        msg = ORCH.reload_prompts()
                        gdb.write(msg + "\n")
                    except Exception as e:
                        gdb.write(f"[copilot] Error reloading prompts: {e}\n")
                else:
                    gdb.write("Usage: /prompts show | /prompts reload\n")
            elif verb == "/colors":
                sub = arg.strip().lower()
                if sub in {"on", "off"}:
                    SESSION.colors_enabled = (sub == "on")
                    gdb.write(f"[copilot] Colors {'enabled' if SESSION.colors_enabled else 'disabled'}\n")
                elif sub == "":
                    gdb.write(f"[copilot] Colors are currently {'on' if SESSION.colors_enabled else 'off'}\n")
                else:
                    gdb.write("Usage: /colors [on|off]\n")
            elif verb == "/debuginfod":
                sub = arg.strip().lower()
                if sub in {"on", "off"}:
                    out = BACKEND.run_command(f"set debuginfod enabled {sub}")
                    gdb.write(out + "\n")
                elif sub == "":
                    out = BACKEND.run_command("show debuginfod enabled")
                    gdb.write(out + "\n")
                else:
                    gdb.write("Usage: /debuginfod [on|off]\n")
            elif verb == "/llm":
                parts = arg.split() if arg else []
                action = parts[0] if parts else ""
                from dbgcopilot.llm import providers as _prov
                sel = SESSION.selected_provider
                if action == "list":
                    gdb.write("Available LLM providers:\n")
                    for p in _prov.list_providers():
                        gdb.write(f"- {p}\n")
                elif action == "use" and len(parts) >= 2:
                    name = parts[1]
                    if _prov.get_provider(name) is None:
                        gdb.write(f"[copilot] Unknown provider: {name}\n")
                    else:
                        SESSION.selected_provider = name
                        gdb.write(f"[copilot] Selected provider: {name}\n")
                elif action == "models":
                    provider = parts[1] if len(parts) >= 2 else (sel or "")
                    if not provider:
                        gdb.write("[copilot] No provider selected. Use /llm use <name> first or pass a provider.\n")
                    elif provider == "openrouter":
                        try:
                            from dbgcopilot.llm import openrouter as _or
                            models = _or.list_models(SESSION.config)
                            if not models:
                                gdb.write("[copilot] No models returned. You may need to set an API key.\n")
                            else:
                                gdb.write("OpenRouter models:\n")
                                for m in models:
                                    gdb.write(f"- {m}\n")
                        except Exception as e:
                            gdb.write(f"[copilot] Error listing models: {e}\n")
                    elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
                        try:
                            from dbgcopilot.llm import openai_compat as _oa
                            models = _oa.list_models(SESSION.config, name=provider)
                            if not models:
                                gdb.write(f"[copilot] No models returned from {provider}. Some providers do not support model listing via API; you can still set a model with /llm model.\n")
                            else:
                                gdb.write(f"{provider} models:\n")
                                for m in models:
                                    gdb.write(f"- {m}\n")
                        except Exception as e:
                            gdb.write(f"[copilot] Error listing models for {provider}: {e}\n")
                    else:
                        gdb.write(f"[copilot] Model listing not supported for provider: {provider}\n")
                elif action == "model":
                    # Set model for provider (default to selected)
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
                        gdb.write("Usage: /llm model [provider] <model>\n")
                    elif provider == "openrouter":
                        SESSION.config["openrouter_model"] = model
                        gdb.write(f"[copilot] OpenRouter model set to: {model}\n")
                    elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
                        key = provider.replace("-", "_") + "_model"
                        SESSION.config[key] = model
                        gdb.write(f"[copilot] {provider} model set to: {model}\n")
                    else:
                        gdb.write(f"[copilot] Setting model not supported for provider: {provider}\n")
                elif action == "key":
                    # /llm key <provider> <api_key>
                    if len(parts) >= 3:
                        provider = parts[1]
                        api_key = " ".join(parts[2:]).strip()
                        if provider == "openrouter":
                            if api_key:
                                SESSION.config["openrouter_api_key"] = api_key
                                gdb.write("[copilot] OpenRouter API key set for this session.\n")
                            else:
                                gdb.write("[copilot] Missing API key.\n")
                        elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "modelscope"}:
                            if api_key:
                                key = provider.replace("-", "_") + "_api_key"
                                SESSION.config[key] = api_key
                                gdb.write(f"[copilot] {provider} API key set for this session.\n")
                            else:
                                gdb.write("[copilot] Missing API key.\n")
                        else:
                            gdb.write(f"[copilot] API key setting not supported for provider: {provider}\n")
                    else:
                        gdb.write("Usage: /llm key <provider> <api_key>\n")
                else:
                    gdb.write(
                        "Usage: /llm list | /llm use <name> | /llm models [provider] | /llm model [provider] <model> | /llm key <provider> <api_key>\n"
                    )
            elif verb == "/exec":
                if not arg:
                    gdb.write("[copilot] Usage: /exec <gdb-cmd>\n")
                else:
                    # Echo the command like GDB does, then output (cyan)
                    if SESSION.colors_enabled:
                        gdb.write(color_text(f"gdb> {arg}", "cyan", bold=True, enable=True) + "\n")
                    else:
                        gdb.write(f"gdb> {arg}\n")
                    out = BACKEND.run_command(arg)
                    SESSION.last_output = out
                    SESSION.attempts.append(Attempt(cmd=arg, output_snippet=out[:160]))
                    gdb.write(out + "\n")
            
            else:
                gdb.write("[copilot] Unknown slash command. Try /help\n")
            continue

        # Natural language: forward to orchestrator.ask
        try:
            resp = ORCH.ask(cmd)
            # Orchestrator already colorizes assistant messages and command echoes based on session setting.
            gdb.write(resp + "\n")
        except Exception as e:
            gdb.write(f"[copilot] Error: {e}\n")

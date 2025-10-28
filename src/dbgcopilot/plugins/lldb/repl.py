"""Nested copilot> REPL for LLDB (packaged).

This REPL expects that `dbgcopilot.plugins.lldb.copilot_cmd` has initialized
global objects and provides the `copilot` command in LLDB.
"""
from __future__ import annotations

try:
    import lldb  # type: ignore
except Exception:  # pragma: no cover
    lldb = None  # type: ignore

from dbgcopilot.core.orchestrator import AgentOrchestrator
from dbgcopilot.core.state import SessionState, Attempt


def _ctx():  # pragma: no cover - lldb environment
    from .copilot_cmd import ORCH, SESSION, BACKEND
    return ORCH, SESSION, BACKEND


def _print_help():
    lines = [
        "copilot> commands:",
        "  /help            Show this help",
        "  /new             Start a new copilot session",
        "  /chatlog         Show chat Q/A transcript",
        "  /prompts show    Show current prompt config",
        "  /prompts reload  Reload prompts from configs/prompts.json",
        "  /config          Show current config",
        "  /agent on|off    Toggle agent mode (auto analysis and final report)",
        "  /exec <cmd>      Run an lldb command and record output",
        "  /llm list                List available LLM providers",
        "  /llm use <name>          Switch to a provider",
    "  /llm models [provider]   List models for provider (default: selected; OpenRouter & OpenAI-compatible)",
    "  /llm model [provider] <model>  Set the model for provider (default: selected; OpenRouter & OpenAI-compatible)",
    "  /llm key <provider> <api_key>  Set API key for provider (stored in-session; OpenRouter & OpenAI-compatible)",
        "  exit or quit     Leave copilot>",
        "Any other input is treated as a natural language question to the LLM.",
    ]
    return "\n".join(lines)


def start_repl():  # pragma: no cover - lldb environment
    ORCH, SESSION, BACKEND = _ctx()
    if ORCH is None or SESSION is None:
        print("[copilot] No active session.")
        return
    print("[copilot] Entering copilot> (type '/help' or 'exit' to leave)")
    while True:
        try:
            line = input("copilot> ")
        except EOFError:
            break
        cmd = (line or "").strip()
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            print("[copilot] Exiting copilot>")
            break
        if cmd.startswith("/"):
            parts = cmd.split(maxsplit=1)
            verb = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if verb in ("/help", "/h"):
                print(_print_help())
            elif verb == "/new":
                import uuid as _uuid
                sid = str(_uuid.uuid4())[:8]
                from .copilot_cmd import SESSION as GLOBAL_SESSION, ORCH as GLOBAL_ORCH, BACKEND as GLOBAL_BACKEND
                new_s = SessionState(session_id=sid)
                globals_mod = __import__("dbgcopilot.plugins.lldb.copilot_cmd", fromlist=["SESSION", "ORCH"])
                setattr(globals_mod, "SESSION", new_s)
                setattr(globals_mod, "ORCH", AgentOrchestrator(GLOBAL_BACKEND, new_s))
                GLOBAL_BACKEND.initialize_session()
                print(f"[copilot] New session: {sid}")
            
            elif verb == "/chatlog":
                if not SESSION.chatlog:
                    print("[copilot] No chat yet.")
                else:
                    for line in SESSION.chatlog[-200:]:
                        print(line)
            elif verb == "/prompts":
                sub = arg.strip().lower()
                if sub == "show":
                    try:
                        cfg = ORCH.get_prompt_config()
                        import json as _json
                        src = cfg.get("_source", "defaults")
                        txt = _json.dumps(cfg, indent=2, ensure_ascii=False)
                        print(f"[copilot] Prompt source: {src}")
                        print(txt)
                    except Exception as e:
                        print(f"[copilot] Error showing prompts: {e}")
                elif sub == "reload":
                    try:
                        msg = ORCH.reload_prompts()
                        print(msg)
                    except Exception as e:
                        print(f"[copilot] Error reloading prompts: {e}")
                else:
                    print("Usage: /prompts show | /prompts reload")
            elif verb == "/config":
                print(f"[copilot] Config: {SESSION.config}")
                print(f"[copilot] Selected provider: {SESSION.selected_provider}")
                print(f"[copilot] Mode: {SESSION.mode}")
            elif verb == "/agent":
                choice = (arg or "").strip().lower()
                if choice not in {"on", "off"}:
                    print("Usage: /agent on|off")
                else:
                    SESSION.mode = "auto" if choice == "on" else "interactive"
                    print(f"[copilot] Agent mode {'enabled' if choice=='on' else 'disabled'}.")
            elif verb == "/exec":
                if not arg:
                    print("[copilot] Usage: /exec <lldb-cmd>")
                else:
                    out = BACKEND.run_command(arg)
                    SESSION.last_output = out
                    SESSION.attempts.append(Attempt(cmd=arg, output_snippet=out[:160]))
                    # Echo similarly to gdb> style for parity
                    print(f"lldb> {arg}")
                    print(out)
            
            elif verb == "/llm":
                # Reuse the same /llm handling as GDB REPL for consistency
                parts2 = arg.split() if arg else []
                action = parts2[0] if parts2 else ""
                from dbgcopilot.llm import providers as _prov
                sel = SESSION.selected_provider
                if action == "list":
                    print("Available LLM providers:")
                    for p in _prov.list_providers():
                        print(f"- {p}")
                elif action == "use" and len(parts2) >= 2:
                    name = parts2[1]
                    if _prov.get_provider(name) is None:
                        print(f"[copilot] Unknown provider: {name}")
                    else:
                        SESSION.selected_provider = name
                        print(f"[copilot] Selected provider: {name}")
                elif action == "models":
                    provider = parts2[1] if len(parts2) >= 2 else (sel or "")
                    if not provider:
                        print("[copilot] No provider selected. Use /llm use <name> first or pass a provider.")
                    elif provider == "openrouter":
                        try:
                            from dbgcopilot.llm import openrouter as _or
                            models = _or.list_models(SESSION.config)
                            if not models:
                                print("[copilot] No models returned. You may need to set an API key.")
                            else:
                                print("OpenRouter models:")
                                for m in models:
                                    print(f"- {m}")
                        except Exception as e:
                            print(f"[copilot] Error listing models: {e}")
                    elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm"}:
                        try:
                            from dbgcopilot.llm import openai_compat as _oa
                            models = _oa.list_models(SESSION.config, name=provider)
                            if not models:
                                print(f"[copilot] No models returned from {provider}. Some providers do not support model listing via API; you can still set a model with /llm model.")
                            else:
                                print(f"{provider} models:")
                                for m in models:
                                    print(f"- {m}")
                        except Exception as e:
                            print(f"[copilot] Error listing models for {provider}: {e}")
                    else:
                        print(f"[copilot] Model listing not supported for provider: {provider}")
                elif action == "model":
                    if len(parts2) == 2:
                        provider = sel
                        model = parts2[1]
                    elif len(parts2) >= 3:
                        provider = parts2[1]
                        model = " ".join(parts2[2:])
                    else:
                        provider = None
                        model = None
                    if not provider or not model:
                        print("Usage: /llm model [provider] <model>")
                    elif provider == "openrouter":
                        SESSION.config["openrouter_model"] = model
                        print(f"[copilot] OpenRouter model set to: {model}")
                    elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm"}:
                        key = provider.replace("-", "_") + "_model"
                        SESSION.config[key] = model
                        print(f"[copilot] {provider} model set to: {model}")
                    else:
                        print(f"[copilot] Setting model not supported for provider: {provider}")
                elif action == "key":
                    if len(parts2) >= 3:
                        provider = parts2[1]
                        api_key = " ".join(parts2[2:]).strip()
                        if provider == "openrouter":
                            if api_key:
                                SESSION.config["openrouter_api_key"] = api_key
                                print("[copilot] OpenRouter API key set for this session.")
                            else:
                                print("[copilot] Missing API key.")
                        elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm"}:
                            if api_key:
                                key = provider.replace("-", "_") + "_api_key"
                                SESSION.config[key] = api_key
                                print(f"[copilot] {provider} API key set for this session.")
                            else:
                                print("[copilot] Missing API key.")
                        else:
                            print(f"[copilot] API key setting not supported for provider: {provider}")
                    else:
                        print("Usage: /llm key <provider> <api_key>")
                else:
                    print(
                        "Usage: /llm list | /llm use <name> | /llm models [provider] | /llm model [provider] <model> | /llm key <provider> <api_key>"
                    )
            else:
                print("[copilot] Unknown slash command. Try /help")
            continue

        # Natural language to orchestrator.ask
        try:
            resp = ORCH.ask(cmd)
            print(resp)
        except Exception as e:
            print(f"[copilot] Error: {e}")

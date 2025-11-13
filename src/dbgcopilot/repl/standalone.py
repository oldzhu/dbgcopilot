"""Standalone copilot> REPL that can launch and control debuggers.

Phase 2a: supports selecting GDB via a subprocess backend. LLDB will be added next.
"""
# pyright: reportConstantRedefinition=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Optional, Any, Dict

from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.core.state import SessionState, Attempt, resolve_auto_round_limit
from dbgcopilot.llm import params as _llm_params
from dbgcopilot.utils.io import color_text


# Globals for a simple REPL
SESSION: Optional[SessionState] = None
BACKEND: Optional[Any] = None
ORCH: Optional[CopilotOrchestrator] = None


def _validate_path(path_input: str) -> tuple[str, Optional[str]]:
    candidate = Path(path_input).expanduser()
    if not candidate.exists():
        return "", f"Path '{path_input}' not found."
    return str(candidate.resolve()), None


def _ensure_session() -> SessionState:
    global SESSION
    if SESSION is None:
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        _install_output_sink(SESSION)
    return SESSION


def _install_output_sink(state: SessionState) -> None:
    def _dbg_sink(chunk: str) -> None:
        if not chunk:
            return
        _echo(chunk)

    def _chat_sink(chunk: str) -> None:
        if not chunk:
            return
        _echo(chunk)

    state.debugger_output_sink = _dbg_sink
    state.chat_output_sink = _chat_sink


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
            "  /use lldb-rust             Select LLDB tuned for Rust binaries",
            "  /use jdb                   Select jdb (Java debugger backend)",
            "  /use pdb                   Select pdb (Python debugger backend)",
            "  /use delve                 Select Delve for Go binaries",
            "  /use radare2               Select radare2 for binary analysis",
            "  /colors on|off             Toggle colored output in REPL and debugger (LLDB/GDB)",
            "  /new                       Start a new copilot session",
            "  /chatlog                   Show chat transcript",
            "  /config                    Show current config",
            "  /auto [on|off|toggle]      Control auto-approve command execution",
            "  /prompts show|reload       Show or reload prompt config",
            "  /exec <cmd>                Run a debugger command (after /use)",
            "  /llm list                  List configured LLM providers",
            "  /llm use <name>            Select provider for this session",
            "  /llm models [provider]     List models (provider must support discovery)",
            "  /llm model [...]           Get/set session or default models",
            "  /llm provider ...          Manage provider definitions (add/set/show)",
            "  /llm params ...            Inspect or tune provider parameters",
            "  /llm key <provider> <key>  Set API key for this session",
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
        return f"Failed to load GDB subprocess backend: {e}"
    BACKEND = GdbSubprocessBackend()
    try:
        BACKEND.initialize_session()
    except Exception as e:
        BACKEND = None
        return f"Failed to start gdb: {e}"
    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    return "Using GDB (subprocess backend)."


def _select_delve() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    try:
        from dbgcopilot.backends.delve_subprocess import DelveSubprocessBackend
    except Exception as e:  # pragma: no cover - import guards runtime dependency
        return f"Failed to load Delve backend: {e}"

    path = input("Enter path to Go binary for Delve: ").strip()
    if not path:
        return "Delve requires a binary path; selection cancelled."

    try:
        BACKEND = DelveSubprocessBackend(program=path)
        BACKEND.initialize_session()
    except Exception as e:
        BACKEND = None
        return f"Failed to start delve: {e}"

    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    s.config["program"] = path
    banner = getattr(BACKEND, "startup_output", "")
    if banner:
        _echo(banner)
    return f"Using Delve (dlv exec {path})."


def _select_radare2() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    try:
        from dbgcopilot.backends.radare2_subprocess import Radare2SubprocessBackend
    except Exception as e:  # pragma: no cover - import guards runtime dependency
        return f"Failed to load radare2 backend: {e}"

    path = input("Enter path to binary for radare2: ").strip()
    if not path:
        return "radare2 requires a binary path; selection cancelled."

    try:
        BACKEND = Radare2SubprocessBackend(program=path)
        BACKEND.initialize_session()
    except Exception as e:
        BACKEND = None
        return f"Failed to start radare2: {e}"

    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    s.config["program"] = path
    banner = getattr(BACKEND, "startup_output", "")
    if banner:
        _echo(banner)
    return f"Using radare2 (-q {path})."


def _select_pdb() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    try:
        from dbgcopilot.backends.python_pdb import PythonPdbBackend
    except Exception as exc:
        return f"Failed to load Python debugger backend: {exc}"

    program = s.config.get("program")

    try:
        BACKEND = PythonPdbBackend(program=program)
        BACKEND.initialize_session()
    except Exception as exc:
        BACKEND = None
        return f"Failed to initialize Python debugger backend: {exc}"

    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    if program:
        s.config["program"] = program
    return "Using pdb (Python debugger backend). Use 'file <script.py>' then 'run' to launch."


def _select_jdb() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    try:
        from dbgcopilot.backends.java_jdb import JavaJdbBackend
    except Exception as exc:
        return f"Failed to load jdb backend: {exc}"

    classpath = s.config.get("classpath")
    sourcepath = s.config.get("sourcepath")
    main_class = s.config.get("jdb_main_class")

    class_prompt = "Enter class path to .class/.jar (required)"
    if classpath:
        class_prompt += f" [current: {classpath}]"
    class_prompt += ": "

    entered_classpath = input(class_prompt).strip()
    if not entered_classpath:
        if not classpath:
            return "jdb setup requires a classpath; selection cancelled."
    else:
        classpath_valid, classpath_error = _validate_path(entered_classpath)
        if classpath_error:
            return classpath_error
        classpath = classpath_valid

    if not classpath:
        return "jdb setup requires a classpath; selection cancelled."

    source_prompt = "Enter source path to .java (optional)"
    if sourcepath:
        source_prompt += f" [current: {sourcepath}]"
    source_prompt += ": "

    entered_source = input(source_prompt).strip()
    if entered_source:
        source_valid, source_error = _validate_path(entered_source)
        if source_error:
            return source_error
        sourcepath = source_valid

    main_prompt = "Enter Main class (optional)"
    if main_class:
        main_prompt += f" [current: {main_class}]"
    main_prompt += ": "
    entered_main = input(main_prompt).strip()
    if entered_main:
        main_class = entered_main

    program = main_class or None

    try:
        BACKEND = JavaJdbBackend(program=program, classpath=classpath, sourcepath=sourcepath)
        BACKEND.initialize_session()
    except Exception as exc:
        BACKEND = None
        return f"Failed to initialize jdb backend: {exc}"

    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    s.config.pop("program", None)
    if classpath:
        s.config["classpath"] = classpath
    else:
        s.config.pop("classpath", None)
    if sourcepath:
        s.config["sourcepath"] = sourcepath
    else:
        s.config.pop("sourcepath", None)
    if main_class:
        s.config["jdb_main_class"] = main_class
    else:
        s.config.pop("jdb_main_class", None)

    details: list[str] = ["Using jdb (Java debugger backend)."]
    if classpath:
        details.append(f"Classpath: {classpath}")
    if sourcepath:
        details.append(f"Sourcepath: {sourcepath}")
    if main_class:
        details.append(f"Main class: {main_class}")
    details.append("Use '/exec run <MainClass>' to launch.")
    return " ".join(details)


def _select_lldb_rust() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    api_error: Optional[Exception] = None
    backend_label = "LLDB (rust-friendly API backend)."

    try:
        from dbgcopilot.backends.lldb_rust_api import LldbRustApiBackend

        BACKEND = LldbRustApiBackend()
        BACKEND.initialize_session()
    except Exception as exc_api:
        api_error = exc_api
        BACKEND = None

    if BACKEND is None:
        backend_label = "LLDB (rust-friendly subprocess backend)."
        try:
            from dbgcopilot.backends.lldb_rust import LldbRustBackend
        except Exception as exc:
            detail = f"Failed to load LLDB Rust backend: {exc}"
            if api_error:
                detail += f"\nAlso failed to load API backend: {api_error}"
            return detail

        try:
            BACKEND = LldbRustBackend()
            BACKEND.initialize_session()
        except Exception as exc:
            BACKEND = None
            detail = f"Failed to start lldb-rust backend: {exc}"
            if api_error:
                detail += f"\nAlso failed to start API backend: {api_error}"
            return detail
        if api_error:
            backend_label += f" (API backend unavailable: {api_error})"
    elif api_error:
        # API succeeded; clear error to avoid stale reference.
        api_error = None

    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    return f"Using {backend_label}"


def _handle_llm(cmd: str) -> str:
    parts = [p for p in (cmd or "").split() if p]
    if not parts:
        return (
            "Usage: /llm list | /llm use <name> | /llm models [provider] | "
            "/llm model [get|set|session] ... | /llm key <provider> <api_key> | "
            "/llm provider <subcommand>"
        )

    from dbgcopilot.llm import providers as _prov

    s = _ensure_session()
    sel = s.selected_provider
    action = parts[0].lower()

    def _usage() -> str:
        return (
            "Usage: /llm list | /llm use <name> | /llm models [provider] | "
            "/llm model [get|set|session] ... | /llm params <action> [...] | "
            "/llm key <provider> <api_key> | /llm provider <subcommand>"
        )

    def _session_model_key(provider: str) -> str:
        if provider == "openrouter":
            return "openrouter_model"
        return provider.replace("-", "_") + "_model"

    def _session_api_key_key(provider: str) -> str:
        if provider == "openrouter":
            return "openrouter_api_key"
        return provider.replace("-", "_") + "_api_key"

    def _format_provider_list(include_header: bool = True) -> str:
        names = _prov.list_providers()
        if not names:
            return "No providers configured. Use /llm provider add to create one."
        lines: list[str] = []
        if include_header:
            lines.append("Available LLM providers:")
        for name in names:
            prov = _prov.get_provider(name)
            marker = "*" if sel == name else "-"
            desc = ""
            if prov is not None:
                desc = prov.meta.get("description") or prov.meta.get("desc") or ""
            line = f"{marker} {name}"
            if desc:
                line += f": {desc}"
            lines.append(line)
        return "\n".join(lines)

    def _handle_provider_subcommand(sub_args: list[str]) -> str:
        import json as _json

        if not sub_args:
            return (
                "Usage: /llm provider list | /llm provider path | /llm provider reload | "
                "/llm provider show <name> | /llm provider get <name> [field] | "
                "/llm provider set <name> <field> <value> | "
                "/llm provider add <name> <base_url> [path] [model] [description]"
            )

        sub = sub_args[0].lower()

        try:
            if sub == "list":
                return _format_provider_list()
            if sub == "path":
                return f"Provider config path: {_prov.config_path()}"
            if sub == "reload":
                _prov.reload()
                return "Provider registry reloaded."
            if sub == "show":
                if len(sub_args) < 2:
                    return "Usage: /llm provider show <name>"
                data = _prov.provider_config(sub_args[1])
                return _json.dumps(data, indent=2, sort_keys=True)
            if sub == "get":
                if len(sub_args) < 2:
                    return "Usage: /llm provider get <name> [field]"
                name = sub_args[1]
                field = sub_args[2] if len(sub_args) >= 3 else None
                value = _prov.get_provider_field(name, field)
                if field:
                    return f"{name}.{field}: {value if value else '(not set)'}"
                return _json.dumps(value, indent=2, sort_keys=True)
            if sub == "set":
                if len(sub_args) < 4:
                    return "Usage: /llm provider set <name> <field> <value>"
                name = sub_args[1]
                field = sub_args[2]
                value = " ".join(sub_args[3:])
                if value.lower() in {"-", "none", "null", "clear"}:
                    value = ""
                updated = _prov.set_provider_field(name, field, value)
                if not value:
                    return f"Cleared {field} for provider: {name}"
                return f"Updated {field} for provider {name}: {updated}"
            if sub == "add":
                if len(sub_args) < 3:
                    return "Usage: /llm provider add <name> <base_url> [path] [model] [description]"
                name = sub_args[1]
                base_url = sub_args[2]
                path = sub_args[3] if len(sub_args) >= 4 else None
                model = sub_args[4] if len(sub_args) >= 5 else None
                description = " ".join(sub_args[5:]) if len(sub_args) >= 6 else ""
                if path in {"-", "none"}:
                    path = None
                if model in {"-", "none"}:
                    model = None
                entry = _prov.add_provider(name=name, base_url=base_url, path=path, default_model=model, description=description)
                snippet = _json.dumps(entry, indent=2, sort_keys=True)
                return f"Added provider '{name}'. Stored in {_prov.config_path()}\n{snippet}"
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Provider command error: {e}"

        return (
            "Usage: /llm provider list | /llm provider path | /llm provider reload | "
            "/llm provider show <name> | /llm provider get <name> [field] | "
            "/llm provider set <name> <field> <value> | /llm provider add <name> <base_url> [path] [model] [description]"
        )

    def _params_usage() -> str:
        return (
            "Usage: /llm params list [provider] | /llm params get [provider] <param> | "
            "/llm params set [provider] <param> <value> | /llm params clear [provider] <param|all>"
        )

    def _is_provider_name(candidate: str) -> bool:
        return _prov.get_provider(candidate) is not None

    def _require_provider(candidate: Optional[str]) -> tuple[str, Any]:
        name = (candidate or "").strip()
        if name:
            prov_obj = _prov.get_provider(name)
            if prov_obj is None:
                raise ValueError(f"Unknown provider: {name}")
            return name, prov_obj
        if sel:
            prov_obj = _prov.get_provider(sel)
            if prov_obj is None:
                raise ValueError(f"Unknown provider: {sel}")
            return sel, prov_obj
        raise ValueError("No provider selected. Use /llm use <name> first or pass a provider.")

    def _capability_matches(meta: Dict[str, Any], original: str, canonical: str) -> bool:
        caps_list = [str(c).lower() for c in _llm_params.list_capabilities(meta)]
        if not caps_list:
            return True
        original_l = original.lower()
        canonical_l = canonical.lower()
        base = canonical.split(".")[-1].lower()
        for cap in caps_list:
            if cap == original_l or cap == canonical_l or cap == base or canonical_l.startswith(cap + "."):
                return True
        return False

    def _handle_params(sub_args: list[str]) -> str:
        if not sub_args:
            return _params_usage()

        sub = sub_args[0].lower()

        if sub in {"help", "?"}:
            return _params_usage()

        if sub == "list":
            provider_name = None
            if len(sub_args) >= 2 and _is_provider_name(sub_args[1]):
                provider_name = sub_args[1]
            try:
                provider_name, provider_obj = _require_provider(provider_name)
            except ValueError as err:
                return str(err)
            caps = sorted([str(c) for c in _llm_params.list_capabilities(provider_obj.meta)], key=str.lower)
            caps_text = ", ".join(caps) if caps else "(none declared)"
            overrides = _llm_params.list_session_params(s.config, provider_name)
            lines = [f"{provider_name} parameter capabilities:", f"- supported: {caps_text}"]
            if overrides:
                lines.append("- session overrides:")
                for canonical, value in sorted(overrides.items()):
                    label = _llm_params.display_name(provider_obj.meta, canonical)
                    prefix = f"  {label}" + (f" [{canonical}]" if label != canonical else "")
                    lines.append(f"{prefix} = {_llm_params.serialize_value(value)}")
            else:
                lines.append("- session overrides: (none)")
            return "\n".join(lines)

        if sub == "get":
            if len(sub_args) < 2:
                return _params_usage()
            args = sub_args[1:]
            if len(args) >= 2 and _is_provider_name(args[0]):
                provider_name = args[0]
                param_name = args[1]
            else:
                provider_name = None
                param_name = args[0]
            try:
                provider_name, provider_obj = _require_provider(provider_name)
                canonical, _ = _llm_params.canonicalize_param(provider_obj.meta, param_name)
            except ValueError as err:
                return str(err)
            overrides = _llm_params.get_session_params(s.config, provider_name)
            label = _llm_params.display_name(provider_obj.meta, canonical)
            if canonical in overrides:
                value = _llm_params.serialize_value(overrides[canonical])
                return f"{provider_name} {label}: {value}"
            defaults = provider_obj.meta.get("default_params")
            if isinstance(defaults, dict) and canonical in defaults:
                value = _llm_params.serialize_value(defaults[canonical])
                return f"No session override. Default {provider_name} {label}: {value}"
            return f"No session override set for {provider_name} {label}."

        if sub == "set":
            if len(sub_args) < 3:
                return _params_usage()
            args = sub_args[1:]
            if len(args) >= 3 and _is_provider_name(args[0]):
                provider_candidate = args[0]
                param_name = args[1]
                raw_value = " ".join(args[2:])
            else:
                provider_candidate = None
                param_name = args[0]
                raw_value = " ".join(args[1:]) if len(args) > 1 else ""
            if not raw_value:
                return _params_usage()
            try:
                provider_name, provider_obj = _require_provider(provider_candidate)
                canonical, value, cleared = _llm_params.parse_value(provider_obj.meta, param_name, raw_value)
            except ValueError as err:
                return str(err)
            label = _llm_params.display_name(provider_obj.meta, canonical)
            if cleared:
                removed = _llm_params.clear_session_param(s.config, provider_name, canonical)
                if removed:
                    return f"Cleared session override for {provider_name} {label}."
                return f"No session override to clear for {provider_name} {label}."
            _llm_params.set_session_param(s.config, provider_name, canonical, value)
            value_txt = _llm_params.serialize_value(value)
            note = ""
            if not _capability_matches(provider_obj.meta, param_name, canonical):
                note = " (provider did not declare this parameter)"
            return f"Session override for {provider_name} {label} set to {value_txt}{note}"

        if sub == "clear":
            if len(sub_args) < 2:
                return _params_usage()
            args = sub_args[1:]
            if len(args) >= 2 and _is_provider_name(args[0]):
                provider_candidate = args[0]
                target = args[1]
            else:
                provider_candidate = None
                target = args[0]
            try:
                provider_name, provider_obj = _require_provider(provider_candidate)
            except ValueError as err:
                return str(err)
            if target.lower() in {"all", "*"}:
                removed = _llm_params.clear_all_session_params(s.config, provider_name)
                if removed:
                    return f"Cleared all session overrides for {provider_name}."
                return f"No session overrides to clear for {provider_name}."
            try:
                canonical, _ = _llm_params.canonicalize_param(provider_obj.meta, target)
            except ValueError as err:
                return str(err)
            label = _llm_params.display_name(provider_obj.meta, canonical)
            removed = _llm_params.clear_session_param(s.config, provider_name, canonical)
            if removed:
                return f"Cleared session override for {provider_name} {label}."
            return f"No session override to clear for {provider_name} {label}."

        return _params_usage()

    if action == "list":
        return _format_provider_list()

    if action == "use" and len(parts) >= 2:
        name = parts[1]
        if _prov.get_provider(name) is None:
            return f"Unknown provider: {name}"
        s.selected_provider = name
        s.config["llm_provider"] = name
        return f"Selected provider: {name}"

    if action == "models":
        provider = parts[1] if len(parts) >= 2 else (sel or "")
        if not provider:
            return "No provider selected. Use /llm use <name> first or pass a provider."
        if _prov.get_provider(provider) is None:
            return f"Unknown provider: {provider}"
        try:
            models = _prov.list_models(provider, session_config=s.config)
        except Exception as e:
            return f"Error listing models for {provider}: {e}"
        if not models:
            return f"{provider} does not expose model listing via API."
        lines = [f"{provider} models:"] + [f"- {m}" for m in models]
        return "\n".join(lines)

    if action == "model":
        if len(parts) == 1:
            provider = sel or ""
            if not provider:
                return "No provider selected. Use /llm use <name> first or pass a provider."
            try:
                default_model = _prov.get_provider_field(provider, "model")
            except ValueError as e:
                return str(e)
            session_override = s.config.get(_session_model_key(provider))
            lines = [f"{provider} default model: {default_model or '(not set)'}"]
            if session_override:
                lines.append(f"Session override: {session_override}")
            return "\n".join(lines)

        sub = parts[1].lower()

        if sub == "get":
            provider = parts[2] if len(parts) >= 3 else (sel or "")
            if not provider:
                return "No provider selected. Use /llm use <name> first or pass a provider."
            try:
                default_model = _prov.get_provider_field(provider, "model")
            except ValueError as e:
                return str(e)
            session_override = s.config.get(_session_model_key(provider))
            lines = [f"{provider} default model: {default_model or '(not set)'}"]
            if session_override:
                lines.append(f"Session override: {session_override}")
            return "\n".join(lines)

        if sub == "set":
            if len(parts) == 3:
                provider = sel or ""
                model = parts[2]
            elif len(parts) >= 4:
                provider = parts[2]
                model = " ".join(parts[3:])
            else:
                provider = ""
                model = ""
            if not provider or not model:
                return "Usage: /llm model set [provider] <model>"
            if model.lower() in {"-", "none", "clear"}:
                model = ""
            try:
                _prov.set_provider_field(provider, "model", model)
            except ValueError as e:
                return str(e)
            if not model:
                return f"Default model for {provider} cleared."
            return f"Default model for {provider} set to: {model}"

        if sub in {"session", "override"}:
            if len(parts) <= 2:
                return "Usage: /llm model session [provider] <model>"
            if len(parts) == 3:
                provider = sel or ""
                model = parts[2]
            else:
                provider = parts[2]
                model = " ".join(parts[3:])
            if not provider:
                return "No provider selected. Use /llm use <name> first or pass a provider."
            if model.lower() in {"-", "none", "clear"}:
                s.config.pop(_session_model_key(provider), None)
                return f"Session model override cleared for {provider}."
            s.config[_session_model_key(provider)] = model
            return f"Session model override for {provider} set to: {model}"

        # Legacy fallback: treat as setting session override (maintains backwards compatibility)
        if len(parts) == 2:
            provider = sel or ""
            model = parts[1]
        else:
            provider = parts[1]
            model = " ".join(parts[2:])
        if not provider or not model:
            return "Usage: /llm model [get|set|session] ..."
        s.config[_session_model_key(provider)] = model
        return (
            f"Session model override for {provider} set to: {model}"
            " (legacy syntax; prefer /llm model session ...)"
        )

    if action == "key":
        if len(parts) < 3:
            return "Usage: /llm key <provider> <api_key>"
        provider_input = parts[1]
        api_key = " ".join(parts[2:]).strip()
        if not provider_input:
            return "Usage: /llm key <provider> <api_key>"
        try:
            provider, _ = _require_provider(provider_input)
        except ValueError as err:
            return str(err)
        if api_key.lower() in {"-", "none", "clear"}:
            s.config.pop(_session_api_key_key(provider), None)
            return f"API key cleared for {provider} (session only)."
        s.config[_session_api_key_key(provider)] = api_key
        return f"{provider} API key set for this session."

    if action == "provider":
        return _handle_provider_subcommand(parts[1:])

    if action == "params":
        return _handle_params(parts[1:])

    return _usage()


def _select_lldb() -> str:
    global BACKEND, ORCH
    s = _ensure_session()
    # Prefer the LLDB Python API backend (robust capture) and fall back to the
    # subprocess backend only if the Python module isn't available.
    try:
        from dbgcopilot.backends.lldb_api import LldbApiBackend
        BACKEND = LldbApiBackend()
        BACKEND.initialize_session()
        ORCH = CopilotOrchestrator(BACKEND, s)
        _install_output_sink(s)
        return "Using LLDB (API backend)."
    except Exception as api_err:
        try:
            from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend
        except Exception as e:
            return (
                f"Failed to load LLDB backends: API error: {api_err}; subprocess import error: {e}\n"
                + _lldb_install_hint()
            )
        BACKEND = LldbSubprocessBackend()
        try:
            BACKEND.initialize_session()
        except Exception as sub_err:
            BACKEND = None
            return (
                f"Failed to start lldb (API error: {api_err}); subprocess error: {sub_err}\n"
                + _lldb_install_hint()
            )
    ORCH = CopilotOrchestrator(BACKEND, s)
    _install_output_sink(s)
    return "Using LLDB (subprocess backend; Python API unavailable).\n" + _lldb_install_hint()


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_session()
    _echo(
    "Standalone REPL. Type /help. Choose a debugger with /use <debugger> "
    "(gdb|lldb|lldb-rust|jdb|pdb|delve|radare2)."
    )
    while True:
        try:
            line = input("copilot> ")
        except EOFError:
            _echo("Exiting copilot>")
            return 0
        except KeyboardInterrupt:
            _echo("^C")
            continue
        cmd = (line or "").strip()
        if not cmd:
            continue
        if cmd in {"exit", "quit"}:
            _echo("Exiting copilot>")
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
                elif choice == "lldb-rust":
                    _echo(_select_lldb_rust())
                elif choice in {"pdb", "python"}:
                    _echo(_select_pdb())
                elif choice == "jdb":
                    _echo(_select_jdb())
                elif choice == "delve":
                    _echo(_select_delve())
                elif choice == "radare2":
                    _echo(_select_radare2())
                else:
                    _echo("Supported: /use gdb | /use lldb | /use lldb-rust | /use jdb | /use pdb | /use delve | /use radare2")
                continue
            if verb == "/new":
                sid = str(uuid.uuid4())[:8]
                globals()["SESSION"] = SessionState(session_id=sid)
                if ORCH is not None and BACKEND is not None:
                    globals()["ORCH"] = CopilotOrchestrator(BACKEND, globals()["SESSION"])  # reload prompts per session
                    _install_output_sink(globals()["SESSION"])
                _echo(f"New session: {sid}")
                continue
            
            if verb == "/chatlog":
                s = _ensure_session()
                if not s.chatlog:
                    _echo("No chat yet.")
                else:
                    for line in s.chatlog[-200:]:
                        _echo(line)
                continue
            if verb == "/config":
                s = _ensure_session()
                _echo(f"Config: {s.config}")
                _echo(f"Selected provider: {s.selected_provider}")
                continue
            if verb in {"/auto", "/autoapprove", "/auto-approve"}:
                choice = (arg or "").strip().lower()
                s = _ensure_session()
                if choice in {"", "status"}:
                    status = "enabled" if s.auto_accept_commands else "disabled"
                    detail = ""
                    if s.auto_accept_commands:
                        remaining = s.auto_rounds_remaining
                        if remaining is not None:
                            detail = f" ({remaining} rounds remaining)"
                    _echo(f"Auto-approve is currently {status}{detail}. Use /auto on|off to change it.")
                    continue
                if choice in {"on", "enable", "enabled"}:
                    if s.auto_accept_commands:
                        _echo("Auto-approve already enabled.")
                        continue
                    s.auto_accept_commands = True
                    s.config["auto_accept_commands"] = "true"
                    limit = resolve_auto_round_limit(s.config)
                    s.auto_rounds_remaining = limit
                    _echo(
                        f"Auto-approve enabled (limit {limit} rounds): suggested commands will run without prompting."
                    )
                    continue
                if choice in {"off", "disable", "disabled"}:
                    if not s.auto_accept_commands:
                        _echo("Auto-approve already disabled.")
                        continue
                    s.auto_accept_commands = False
                    s.config.pop("auto_accept_commands", None)
                    s.auto_rounds_remaining = None
                    _echo("Auto-approve disabled: confirmations required before running commands.")
                    continue
                if choice == "toggle":
                    if s.auto_accept_commands:
                        s.auto_accept_commands = False
                        s.config.pop("auto_accept_commands", None)
                        s.auto_rounds_remaining = None
                        _echo("Auto-approve disabled.")
                    else:
                        s.auto_accept_commands = True
                        s.config["auto_accept_commands"] = "true"
                        limit = resolve_auto_round_limit(s.config)
                        s.auto_rounds_remaining = limit
                        _echo(f"Auto-approve enabled (limit {limit} rounds).")
                    continue
                _echo("Usage: /auto [on|off|toggle|status]")
                continue
            if verb == "/agent":
                _echo("Agent mode has moved to the new dbgagent tool.")
                continue
            if verb == "/prompts":
                if arg.strip().lower() == "show":
                    try:
                        if ORCH is None:
                            _echo("No debugger selected.")
                        else:
                            cfg = ORCH.get_prompt_config()
                            import json as _json
                            src = cfg.get("_source", "defaults")
                            txt = _json.dumps(cfg, indent=2, ensure_ascii=False)
                            _echo(f"Prompt source: {src}")
                            _echo(txt)
                    except Exception as e:
                        _echo(f"Error showing prompts: {e}")
                elif arg.strip().lower() == "reload":
                    try:
                        if ORCH is None:
                            _echo("No debugger selected.")
                        else:
                            _echo(ORCH.reload_prompts())
                    except Exception as e:
                        _echo(f"Error reloading prompts: {e}")
                else:
                    _echo("Usage: /prompts show | /prompts reload")
                continue
            if verb == "/exec":
                if BACKEND is None:
                    _echo("No debugger selected. Use /use gdb first.")
                elif not arg:
                    _echo("Usage: /exec <cmd>")
                else:
                    label = getattr(BACKEND, "name", "debugger") or "debugger"
                    s = _ensure_session()
                    prompt = getattr(BACKEND, "prompt", "") or ""
                    if prompt:
                        line = f"{prompt.rstrip()} {arg}".rstrip()
                    else:
                        line = f"{label}> {arg}"
                    _echo(color_text(line, "cyan", bold=True, enable=True) if s.colors_enabled else line)
                    try:
                        out = BACKEND.run_command(arg)
                    except Exception as e:
                        out = f"Error: {e}"
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
                _echo(f"Colors {'enabled' if enable else 'disabled'}.")
                continue
            
            if verb == "/llm":
                _echo(_handle_llm(arg))
                continue
            _echo("Unknown slash command. Try /help")
            continue

        # Natural language → orchestrator
        if ORCH is None:
            _echo("No debugger selected. Use /use gdb first.")
            continue
        try:
            resp = ORCH.ask(cmd)
            if resp:
                _echo(resp)
        except Exception as e:
            _echo(f"Error: {e}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

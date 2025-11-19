"""Core execution loop for dbgagent."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, Callable, cast, Iterable
import logging
import uuid
import re

from dbgcopilot.core.state import Attempt
from dbgcopilot.utils.io import head_tail_truncate, strip_ansi
from dbgcopilot.llm import providers

from .prompts import AGENT_PROMPT_CONFIG


@dataclass
class AgentRequest:
    debugger: str
    provider: str
    model: Optional[str]
    api_key: Optional[str]
    program: Optional[str]
    classpath: Optional[str]
    sourcepath: Optional[str]
    main_class: Optional[str]
    corefile: Optional[str]
    goal_type: str
    goal_text: str
    resume_context: Optional[str]
    max_steps: int
    language: str
    log_enabled: bool
    log_path: Optional[Path]
    report_path: Path


@dataclass
class AgentState:
    session_id: str
    attempts: list[Attempt] = field(default_factory=list)
    chatlog: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    last_output: str = ""


class DebugAgentRunner:
    """Coordinate autonomous debugging for a single session."""

    def __init__(self, request: AgentRequest) -> None:
        self.request = request
        self.state = AgentState(session_id=str(uuid.uuid4())[:8])
        self.prompt_config: Dict[str, Any] = dict(AGENT_PROMPT_CONFIG)
        self.session_config: dict[str, str] = {}
        self.logger = logging.getLogger(f"dbgagent.session.{self.state.session_id}")
        self.logger.setLevel(logging.INFO)
        self._handler: Optional[logging.Handler] = None
        self._provider_cache: Dict[str, Callable[[str], str]] = {}
        self.usage_entries: list[Dict[str, Any]] = []
        self.usage_totals: Dict[str, float] = {
            "prompt_tokens": 0.0,
            "completion_tokens": 0.0,
            "total_tokens": 0.0,
            "cost": 0.0,
        }
        if self.request.log_enabled and self.request.log_path is not None:
            self.request.log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(self.request.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            self.logger.addHandler(handler)
            self._handler = handler
        # Seed context from resume file if provided
        if self.request.resume_context:
            self.state.facts.append("Prior session summary:")
            for line in self.request.resume_context.strip().splitlines():
                self.state.facts.append(f"  {line.strip()}")

        # Prepare provider-specific configuration
        provider_key = self.request.provider.replace("-", "_")
        if self.request.model:
            self.session_config[f"{provider_key}_model"] = self.request.model
        if self.request.api_key:
            self.session_config[f"{provider_key}_api_key"] = self.request.api_key

        if self.request.program:
            self.state.facts.append(f"Program path: {self.request.program}")
        if self.request.corefile:
            self.state.facts.append(f"Corefile: {self.request.corefile}")
        if self.request.debugger == "jdb":
            if self.request.classpath:
                self.state.facts.append(f"JDB classpath: {self.request.classpath}")
            if self.request.sourcepath:
                self.state.facts.append(f"JDB sourcepath: {self.request.sourcepath}")
            if self.request.main_class:
                self.state.facts.append(f"JDB main class: {self.request.main_class}")

        self.backend = None

    # ------------------------------------------------------------------
    def run(self) -> str:
        try:
            self._log(f"Starting dbgagent session {self.state.session_id}")
            self._log(f"Debugger: {self.request.debugger}")
            self._log(f"Provider: {self.request.provider} | Model: {self.request.model or '(default)'}")
            self._log(f"Goal: {self.request.goal_type} | Notes: {self.request.goal_text or '(none)'}")
            self._log(f"Language: {self.request.language}")
            if self.request.debugger == "jdb":
                self._log(f"Classpath: {self.request.classpath or '(unset)'}")
                self._log(f"Main class: {self.request.main_class or '(unset)'}")
                if self.request.sourcepath:
                    self._log(f"Sourcepath: {self.request.sourcepath}")
            else:
                if self.request.program:
                    self._log(f"Program: {self.request.program}")
                if self.request.corefile:
                    self._log(f"Corefile: {self.request.corefile}")
            self.backend = self._create_backend()
            self._prepare_debugger()
            final_report = self._auto_loop()
            self._write_report(final_report)
            return final_report
        finally:
            if self._handler is not None:
                self.logger.removeHandler(self._handler)
                self._handler.close()

    # ------------------------------------------------------------------
    def _create_backend(self):
        debugger = self.request.debugger
        if debugger == "gdb":
            from dbgcopilot.backends.gdb_subprocess import GdbSubprocessBackend

            backend = GdbSubprocessBackend()
            backend.initialize_session()
        elif debugger == "lldb":
            backend = self._create_lldb_backend()
        elif debugger == "lldb-rust":
            backend = self._create_lldb_rust_backend()
        elif debugger == "delve":
            if not self.request.program:
                raise ValueError("Delve debugger requires a program path")
            from dbgcopilot.backends.delve_subprocess import DelveSubprocessBackend

            backend = DelveSubprocessBackend(program=self.request.program)
            backend.initialize_session()
        elif debugger == "radare2":
            if not self.request.program:
                raise ValueError("radare2 debugger requires a program path")
            from dbgcopilot.backends.radare2_subprocess import Radare2SubprocessBackend

            backend = Radare2SubprocessBackend(program=self.request.program)
            backend.initialize_session()
        elif debugger == "pdb":
            if not self.request.program:
                raise ValueError("pdb debugger requires a Python script path")
            from dbgcopilot.backends.python_pdb import PythonPdbBackend

            backend = PythonPdbBackend(program=self.request.program)
            backend.initialize_session()
        elif debugger == "jdb":
            from dbgcopilot.backends.java_jdb import JavaJdbBackend

            backend = JavaJdbBackend(
                program=self.request.main_class,
                classpath=self.request.classpath,
                sourcepath=self.request.sourcepath,
            )
            backend.initialize_session()
        else:
            raise ValueError(f"Unsupported debugger: {debugger}")

        backend_name = getattr(backend, "name", backend.__class__.__name__)
        self._log(f"Using debugger backend: {backend_name}")
        self.state.facts.append(f"Debugger backend: {backend_name}")

        startup = getattr(backend, "startup_output", "")
        if isinstance(startup, str) and startup.strip():
            self.state.facts.append(startup.strip())

        return backend

    def _create_lldb_backend(self):
        api_error: Optional[Exception] = None
        try:
            from dbgcopilot.backends.lldb_api import LldbApiBackend

            backend = LldbApiBackend()
            backend.initialize_session()
            self._log("Selected LLDB API backend")
            return backend
        except Exception as exc:
            api_error = exc

        try:
            import lldb  # type: ignore

            if getattr(lldb, "debugger", None):
                from dbgcopilot.backends.lldb_inprocess import LldbInProcessBackend

                backend = LldbInProcessBackend()
                backend.initialize_session()
                self._log("Selected LLDB in-process backend")
                return backend
        except Exception:
            pass

        from dbgcopilot.backends.lldb_subprocess import LldbSubprocessBackend

        backend = LldbSubprocessBackend()
        backend.initialize_session()
        if api_error:
            self._log(f"LLDB API backend unavailable, using subprocess backend: {api_error}")
        else:
            self._log("Selected LLDB subprocess backend")
        return backend

    def _create_lldb_rust_backend(self):
        api_error: Optional[Exception] = None
        try:
            from dbgcopilot.backends.lldb_rust_api import LldbRustApiBackend

            backend = LldbRustApiBackend()
            backend.initialize_session()
            self._log("Selected LLDB Rust API backend")
            return backend
        except Exception as exc:
            api_error = exc

        from dbgcopilot.backends.lldb_rust import LldbRustBackend

        backend = LldbRustBackend()
        backend.initialize_session()
        if api_error:
            self._log(
                f"LLDB Rust API backend unavailable, using subprocess backend: {api_error}"
            )
        else:
            self._log("Selected LLDB Rust subprocess backend")
        return backend

    def _prepare_debugger(self) -> None:
        if self.backend is None:
            return
        self._log("Preparing debugger session")
        commands: list[str] = []
        debugger = self.request.debugger

        if debugger == "gdb":
            if self.request.program:
                commands.append(f"file {self.request.program}")
            if self.request.corefile:
                commands.append(f"core-file {self.request.corefile}")
        elif debugger in {"lldb", "lldb-rust"}:
            if self.request.program and self.request.corefile:
                commands.append(
                    f"target create {self.request.program} --core {self.request.corefile}"
                )
            elif self.request.corefile:
                commands.append(f"target create --core {self.request.corefile}")
            elif self.request.program:
                commands.append(f"target create {self.request.program}")
        elif debugger == "pdb":
            if self.request.program:
                commands.append(f"file {self.request.program}")
        elif debugger == "jdb":
            details: list[str] = []
            if self.request.classpath:
                details.append(f"classpath={self.request.classpath}")
            if self.request.sourcepath:
                details.append(f"sourcepath={self.request.sourcepath}")
            if self.request.main_class:
                details.append(f"main_class={self.request.main_class}")
            if details:
                self.state.facts.append("JDB configuration: " + ", ".join(details))
            return
        else:
            # Delve and radare2 perform program loading during initialization.
            return

        for cmd in commands:
            out = self.backend.run_command(cmd)
            self._record_execution(cmd, out)

    # ------------------------------------------------------------------
    def _auto_loop(self) -> str:
        max_steps_value = self.prompt_config.get("max_steps", self.request.max_steps)
        try:
            max_steps = int(max_steps_value)
        except Exception:
            max_steps = self.request.max_steps

        dbg = getattr(self.backend, "name", self.request.debugger)
        system_template = str(self.prompt_config.get("system_preamble", ""))
        try:
            system_preamble = system_template.format(debugger=dbg)
        except Exception:
            system_preamble = system_template

        rules_value = self.prompt_config.get("rules", [])
        if isinstance(rules_value, (list, tuple)):
            iterable_rules = cast(Iterable[Any], rules_value)
            rendered_rules = [f"- {item}" for item in iterable_rules]
            rules_text = "\n".join(rendered_rules)
        else:
            rules_text = ""

        followup = str(self.prompt_config.get("followup_instruction", ""))
        language_instruction = self._language_instruction()

        for step in range(1, max_steps + 1):
            prompt = self._build_prompt(system_preamble, rules_text, followup, language_instruction)
            answer = self._call_llm(prompt)
            answer_clean = answer.strip()
            self._log(f"LLM step {step} response:\n{answer_clean}")
            self.state.chatlog.append(f"Assistant: {answer_clean}")

            cmd = self._extract_cmd(answer_clean)
            if cmd:
                self._log(f"Executing command: {cmd}")
                if self.backend is None:
                    raise RuntimeError("Debugger backend not initialized")
                out = self.backend.run_command(cmd)
                self._record_execution(cmd, out)
                continue

            if not answer_clean:
                continue
            # Treat as final report
            return answer_clean

        # Max steps reached without final report
        self._log("Reached maximum iterations without final report")
        return self._fallback_report()

    # ------------------------------------------------------------------
    def _build_prompt(self, system_preamble: str, rules_text: str, followup: str, language_instruction: str) -> str:
        context_lines: list[str] = []
        context_lines.append(f"Goal category: {self.request.goal_type}")
        if self.request.goal_text:
            context_lines.append(f"Goal notes: {self.request.goal_text}")
        if self.request.resume_context:
            context_lines.append("Loaded prior report:")
            context_lines.append(self.request.resume_context.strip())
        if self.state.facts:
            context_lines.append("Recent observations:")
            context_lines.extend(self.state.facts[-10:])
        if self.state.attempts:
            recent_cmds = [f"- {a.cmd}: {a.output_snippet[:160]}" for a in self.state.attempts[-5:]]
            context_lines.append("Recent commands:")
            context_lines.extend(recent_cmds)
        if self.state.last_output:
            context_lines.append("Latest debugger output:")
            context_lines.append(head_tail_truncate(self.state.last_output, 1200))

        context_block = "\n".join(context_lines)
        prompt_parts = [system_preamble]
        if rules_text:
            prompt_parts.append("Rules:\n" + rules_text)
        if language_instruction:
            prompt_parts.append(language_instruction)
        if context_block:
            prompt_parts.append("Context:\n" + context_block)
        prompt_parts.append("User: " + followup)
        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)

    def _language_instruction(self) -> str:
        lang = (self.request.language or "en").lower()
        if lang in {"en", "en-us", "en-gb", "english"}:
            return "Respond in English. Do not switch languages unless explicitly requested."
        if lang in {"zh", "zh-cn", "zh-hans", "chinese", "zh-cn"}:
            return "请使用简体中文回答，并且仅在收到明确指示时切换语言。"
        return f"Respond in {self.request.language}. Do not switch languages unless explicitly requested."

    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str) -> str:
        provider = self.request.provider
        ask_fn = self._get_provider_fn(provider)
        answer = ask_fn(prompt)
        usage = getattr(ask_fn, "last_usage", None)
        self._record_usage_stats(provider, usage)
        return answer

    # ------------------------------------------------------------------
    def _extract_cmd(self, text: str) -> Optional[str]:
        match = re.search(r"<cmd>\s*([\s\S]*?)\s*</cmd>", text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip()

    def _get_provider_fn(self, provider: str) -> Callable[[str], str]:
        if provider in self._provider_cache:
            return self._provider_cache[provider]

        if provider == "openrouter":
            from dbgcopilot.llm import openrouter as _or

            ask_fn = _or.create_provider(session_config=self.session_config)
        elif provider in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "llama-cpp", "modelscope"}:
            from dbgcopilot.llm import openai_compat as _oa

            ask_fn = _oa.create_provider(session_config=self.session_config, name=provider)
        else:
            prov = providers.get_provider(provider)
            if prov is None:
                raise RuntimeError(f"Unknown provider: {provider}")
            ask_fn = prov.ask

        self._provider_cache[provider] = ask_fn
        return ask_fn

    def _record_usage_stats(self, provider: str, usage: Any) -> None:
        if not isinstance(usage, dict) or not usage:
            return

        usage_dict: Dict[str, Any] = cast(Dict[str, Any], usage)

        entry: Dict[str, Any] = {
            "provider": usage_dict.get("provider") or provider,
            "model": usage_dict.get("model") or self.request.model or "(default)",
        }

        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = usage_dict.get(key)
            if val is None:
                continue
            try:
                intval = int(val)
            except Exception:
                continue
            entry[key] = intval
            self.usage_totals[key] = self.usage_totals.get(key, 0.0) + intval

        cost_val = usage_dict.get("cost")
        if cost_val is not None:
            try:
                cost_float = float(cost_val)
                entry["cost"] = cost_float
                self.usage_totals["cost"] = self.usage_totals.get("cost", 0.0) + cost_float
            except Exception:
                pass

        self.usage_entries.append(entry)

        msg_parts = [f"provider={entry['provider']}", f"model={entry['model']}"]
        if "prompt_tokens" in entry:
            msg_parts.append(f"prompt_tokens={entry['prompt_tokens']}")
        if "completion_tokens" in entry:
            msg_parts.append(f"completion_tokens={entry['completion_tokens']}")
        if "total_tokens" in entry:
            msg_parts.append(f"total_tokens={entry['total_tokens']}")
        if "cost" in entry:
            msg_parts.append(f"cost=${entry['cost']:.6f}")
        self._log("LLM usage: " + ", ".join(msg_parts))

    def _record_execution(self, cmd: str, output: str) -> None:
        clean_output = strip_ansi(output or "")
        snippet = clean_output[:160]
        self.state.attempts.append(Attempt(cmd=cmd, output_snippet=snippet))
        self.state.last_output = clean_output
        if clean_output:
            first_line = clean_output.splitlines()[0]
        else:
            first_line = "(no output)"
        self.state.facts.append(f"Executed {cmd!r}: {first_line}")
        self.state.chatlog.append(f"Assistant: (executed) {cmd}\n" + clean_output)
        self._log(f"Output:\n{clean_output.strip() if clean_output else '(no output)'}")

    def _fallback_report(self) -> str:
        lines = [
            "Final Report",
            "Analysis Summary:\n- Reached max iterations without definitive conclusion.",
            "Findings:\n- Review executed commands and captured outputs above for clues.",
            "Suggested Fixes:\n- Collect additional data or adjust dbgagent max-steps to continue.",
            "Next Steps:\n- Provide more context or inspect the latest output manually.",
        ]
        return "\n\n".join(lines)

    def _write_report(self, final_report: str) -> None:
        self.request.report_path.parent.mkdir(parents=True, exist_ok=True)
        content_lines = [
            f"# dbgagent report — {self.state.session_id}",
            "",
            f"Goal: {self.request.goal_type}",
            f"Goal notes: {self.request.goal_text or '(none)'}",
            "",
            "## Final Report",
            final_report.strip(),
        ]
        backend_name = getattr(self.backend, "name", None) or self.request.debugger
        session_section = [
            "",
            "## Session Details",
            f"Debugger backend: {backend_name}",
            f"LLM provider: {self.request.provider}",
            f"LLM model: {self.request.model or '(default)'}",
            f"Language: {self.request.language}",
            f"Max steps: {self.request.max_steps}",
        ]
        if self.request.log_enabled and self.request.log_path:
            session_section.append(f"Session log: {self.request.log_path}")
        content_lines += session_section
        if self.usage_entries:
            total_prompt = int(self.usage_totals.get("prompt_tokens", 0) or 0)
            total_completion = int(self.usage_totals.get("completion_tokens", 0) or 0)
            total_tokens = int(self.usage_totals.get("total_tokens", 0) or 0)
            total_cost = float(self.usage_totals.get("cost", 0.0) or 0.0)
            content_lines += [
                "",
                "## LLM Usage",
                f"Total prompt tokens: {total_prompt}",
                f"Total completion tokens: {total_completion}",
                f"Total tokens: {total_tokens}",
            ]
            if total_cost:
                content_lines.append(f"Total estimated cost (USD): ${total_cost:.6f}")
            content_lines.append("")
            content_lines.append("Per-call usage:")
            for idx, entry in enumerate(self.usage_entries, start=1):
                parts = [f"provider={entry['provider']}", f"model={entry['model']}"]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if key in entry:
                        parts.append(f"{key}={entry[key]}")
                if "cost" in entry:
                    parts.append(f"cost=${entry['cost']:.6f}")
                content_lines.append(f"- Call {idx}: " + ", ".join(parts))
        content_lines += [
            "",
            "## Executed Commands",
        ]
        if self.state.attempts:
            for attempt in self.state.attempts:
                content_lines.append(f"- `{attempt.cmd}`: {attempt.output_snippet}")
        else:
            content_lines.append("- (none)")
        content_lines += [
            "",
            "## Notes",
            "You can edit this report and pass it back to dbgagent with --resume-from to continue the investigation.",
        ]
        self.request.report_path.write_text("\n".join(content_lines), encoding="utf-8")
        if self.usage_entries:
            total_prompt = int(self.usage_totals.get("prompt_tokens", 0) or 0)
            total_completion = int(self.usage_totals.get("completion_tokens", 0) or 0)
            total_tokens = int(self.usage_totals.get("total_tokens", 0) or 0)
            total_cost = float(self.usage_totals.get("cost", 0.0) or 0.0)
            summary = (
                f"LLM totals — prompt_tokens={total_prompt}, completion_tokens={total_completion}, "
                f"total_tokens={total_tokens}"
            )
            if total_cost:
                summary += f", cost=${total_cost:.6f}"
            self._log(summary)
        self._log(f"Report written to {self.request.report_path}")

    # ------------------------------------------------------------------
    def _log(self, message: str) -> None:
        if self.request.log_enabled and self._handler is not None:
            self.logger.info(message)


__all__ = ["AgentRequest", "AgentState", "DebugAgentRunner"]

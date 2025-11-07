"""Interactive orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnusedFunction=false
from __future__ import annotations

from typing import Optional, List, Any
import re
from dbgcopilot.core.state import Attempt, SessionState
from dbgcopilot.llm import providers
from dbgcopilot.utils.io import head_tail_truncate, color_text, strip_ansi
from pathlib import Path
import os
import json
from dbgcopilot.prompts.defaults import DEFAULT_PROMPT_CONFIG


class CopilotOrchestrator:
    """Placeholder orchestrator.

    In future iterations, this will:
    - Initialize LLM and prompt templates
    - Provide methods for suggest/ask/plan/auto/report
    - Use a Backend to run commands safely
    """

    def __init__(self, backend: Any, state: SessionState):
        self.backend: Any = backend
        self.state: SessionState = state
        # Load prompt config
        self.prompt_source = "defaults"
        self.prompt_config = self._load_prompt_config()

    def _repo_root(self) -> Path:
        here = Path(__file__).resolve()
        # Heuristic for this repo layout: /workspace/src/dbgcopilot/core/orchestrator.py
        # Try parent[4] -> /workspace, else parent[3] -> /workspace/src
        candidates = []
        try:
            candidates.append(here.parents[4])
        except Exception:
            pass
        try:
            candidates.append(here.parents[3])
        except Exception:
            pass
        for c in candidates:
            if (c / "configs").exists():
                return c
        # Fallback to the deepest parent with 'configs'
        for p in here.parents:
            if (p / "configs").exists():
                return p
        return here.parents[-1]

    def _load_prompt_config(self) -> dict[str, Any]:
        """Load prompt config with precedence: env -> profile -> default file -> defaults."""
        cfg = dict(DEFAULT_PROMPT_CONFIG)
        source = "defaults"
        # 1) Env var DBGCOPILOT_PROMPTS (absolute or relative)
        env_path = os.environ.get("DBGCOPILOT_PROMPTS")
        if env_path:
            try:
                p = Path(env_path).expanduser()
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                if p.exists():
                    with p.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        cfg.update(data)
                        source = str(p)
                        self.prompt_source = source
                        return cfg
            except Exception:
                pass
        # 2) Profile-specific file: prompts.<backend>.json
        try:
            profile = getattr(self.backend, "name", "") or ""
        except Exception:
            profile = ""
        root = self._repo_root()
        if profile:
            prof_path = root / "configs" / f"prompts.{profile}.json"
            try:
                if prof_path.exists():
                    with prof_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        cfg.update(data)
                        source = str(prof_path)
                        self.prompt_source = source
                        return cfg
            except Exception:
                pass
        # 3) Default prompts.json in configs
        try:
            cfg_path = root / "configs" / "prompts.json"
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    cfg.update(data)
                    source = str(cfg_path)
        except Exception:
            pass
        self.prompt_source = source
        return cfg

    def reload_prompts(self) -> str:
        self.prompt_config = self._load_prompt_config()
        return f"Prompts reloaded from {self.prompt_source}."

    def get_prompt_config(self) -> dict[str, Any]:
        d = dict(self.prompt_config)
        d["_source"] = self.prompt_source
        return d

    def ask(self, question: str) -> str:
        text = (question or "").strip()
        if getattr(self.state, "pending_command", None):
            return self._handle_command_confirmation(text)
        return self._llm_turn(text)

    def _handle_command_confirmation(self, reply: str) -> str:
        cmd = self.state.pending_command
        self.state.pending_command = None
        if not cmd:
            return self._llm_turn(reply)

        choice = (reply or "").strip().lower()
        if choice in {"y", "yes"}:
            return self._execute_with_followup(cmd)
        if choice in {"a", "auto", "auto yes", "auto-yes"}:
            self.state.auto_accept_commands = True
            self.state.config["auto_accept_commands"] = "true"
            executed = self._execute_with_followup(cmd)
            prefix = "Auto-accept enabled for this session."
            return f"{prefix}\n{executed}" if executed else prefix

        # Treat any other response (including blank) as skip
        return "Command skipped."

    def _execute_with_followup(self, command: str, preface: Optional[str] = None) -> str:
        segments: list[str] = []
        if preface and not self.state.last_answer_streamed:
            colors = getattr(self.state, "colors_enabled", True)
            segments.append(color_text(preface, "green", enable=colors) if colors else preface)
        exec_output, streamed = _execute_once(self, command)
        if exec_output and not streamed:
            segments.append(exec_output)
        followup_prompt = self._build_followup_prompt(command, exec_output)
        followup = self._llm_turn(followup_prompt)
        if followup and not self.state.last_answer_streamed:
            segments.append(followup)
        return "\n".join(seg for seg in segments if seg)

    def _build_followup_prompt(self, command: str, exec_output: str) -> str:
        plain = strip_ansi(exec_output or "")
        parts = [
            f"The debugger command `{command}` was executed.",
            "Debugger output:",
            plain or "(no output)",
            "What should we do next? Remember to wrap any future debugger commands inside <cmd>...</cmd>.",
        ]
        return "\n".join(parts)

    def _format_confirmation_prompt(self, raw_answer: str, command: str) -> str:
        colors = getattr(self.state, "colors_enabled", True)
        explanation = self._extract_explanation(raw_answer)
        parts = []
        if explanation:
            parts.append(color_text(explanation, "green", enable=colors))
        parts.append("Proposed debugger command:")
        label = (getattr(self.backend, "name", "debugger") or "debugger")
        parts.append(_prefix_dbg_echo(command, label=label, colors=colors))
        parts.append("Run it? (y(es)/n(o)/a(uto yes))")
        proposal = {
            "type": "command_proposal",
            "command": command,
            "label": label,
        }
        if explanation:
            proposal["explanation"] = strip_ansi(explanation)
        self.state.pending_chat_events.append(proposal)
        return "\n".join(parts)

    def _extract_explanation(self, raw_answer: str) -> str:
        return re.sub(r"<cmd>[\s\S]*?</cmd>", "", raw_answer, flags=re.IGNORECASE).strip()

    def _emit_chat(self, text: str, *, color: Optional[str] = "green") -> bool:
        if not text:
            self.state.last_answer_streamed = False
            return False
        colors_enabled = getattr(self.state, "colors_enabled", True)
        payload = text
        if color and colors_enabled:
            # Avoid wrapping text that already includes ANSI sequences
            if strip_ansi(text) == text:
                payload = color_text(text, color, enable=colors_enabled)
            else:
                payload = text
        sink = getattr(self.state, "chat_output_sink", None)
        if sink:
            try:
                sink(payload)
                self.state.last_answer_streamed = True
                return True
            except Exception:
                pass
        self.state.pending_chat.append(payload)
        self.state.last_answer_streamed = True
        return True

    def _llm_turn(self, question: str) -> str:
        text = (question or "").strip()

        self.state.last_answer_streamed = False

        dbg = getattr(self.backend, "name", "debugger")
        goal = (self.state.goal or "").strip()

        prev_lines = list(self.state.chatlog)
        prev_lines.append(f"User: {text}")

        MAX_CONTEXT_CHARS = int(self.prompt_config.get("max_context_chars", 16000))
        transcript_for_llm = "\n".join(prev_lines)
        if len(transcript_for_llm) > MAX_CONTEXT_CHARS:
            choice = text.lower()
            if choice in {"summarize and new session", "summarise and new session"}:
                try:
                    prev_summary = _llm_summarize_session(self)
                except Exception:
                    prev_summary = self.summary()
                try:
                    import uuid as _uuid
                    self.state.session_id = str(_uuid.uuid4())[:8]
                except Exception:
                    pass
                self.state.chatlog.clear()
                self.state.attempts.clear()
                self.state.facts.clear()
                self.state.last_output = ""
                if prev_summary:
                    self.state.facts.append(f"Summary: {prev_summary.splitlines()[0][:160]}")
                return (
                    f"Started a new session: {self.state.session_id}\n"
                    "Here is a brief summary of the previous session for reference:\n"
                    + prev_summary
                )
            if choice in {"new session", "start new session", "new"}:
                try:
                    import uuid as _uuid
                    self.state.session_id = str(_uuid.uuid4())[:8]
                except Exception:
                    pass
                self.state.chatlog.clear()
                self.state.attempts.clear()
                self.state.facts.clear()
                self.state.last_output = ""
                return f"Started a fresh session: {self.state.session_id}"
            return (
                "Your session context is quite large. Would you like me to summarize the "
                "current session and start a new one from that summary, or start a fresh session "
                "without a summary? Reply with 'summarize and new session' or 'new session'."
            )
        attempts = self.state.attempts[-5:]
        attempts_txt = "\n".join(
            f"- {a.cmd}: {a.output_snippet}" for a in attempts if getattr(a, "output_snippet", "")
        )
        last_out = head_tail_truncate(self.state.last_output or "", 2000)

        wants_zh = _wants_chinese(question)

        all_rules = list(self.prompt_config.get("rules", []))
        rules_lines = "\n".join(f"- {r}" for r in all_rules)
        system_preamble = (
            self.prompt_config.get("system_preamble", "").format(debugger=dbg)
            + self.prompt_config.get("assistant_cmd_tag_instructions", "")
            + ("Rules:\n" + rules_lines + "\n" if rules_lines else "")
        )

        context_block = (
            (f"Goal: {goal}\n" if goal else "")
            + (f"Recent commands and snippets:\n{attempts_txt}\n" if attempts_txt else "")
            + (f"Last output:\n{last_out}\n" if last_out else "")
            + ("\nFull conversation so far:\n" + "\n".join(self.state.chatlog) + "\n" if self.state.chatlog else "")
        )

        lang_hint = (self.prompt_config.get("language_hint_zh", "") if wants_zh else "")

        primed_question = (
            system_preamble
            + ("\n" + context_block if context_block else "")
            + ("\n" + lang_hint if lang_hint else "")
            + "\nUser: "
            + question.strip()
            + "\nAssistant:"
        )

        pname = getattr(self.state, "selected_provider", None) or self.state.config.get("llm_provider")
        if pname:
            prov = providers.get_provider(pname)
            if prov:
                try:
                    try:
                        client = prov.create_client(self.state.config)
                    except Exception:
                        client = prov.ask
                    answer = client(primed_question)

                    user_line = f"User: {question.strip()}"
                    assistant_line = f"Assistant: {answer.strip()}"
                    self.state.chatlog.append(user_line)
                    self.state.chatlog.append(assistant_line)
                    self.state.facts.append(f"Q: {question.strip()}")
                    self.state.facts.append(f"A: {(answer.splitlines()[0] if answer else '').strip()}")

                    explanation = self._extract_explanation(answer)
                    display_text = (explanation or answer).strip()
                    auto_mode = getattr(self.state, "auto_accept_commands", False)
                    streamed = False
                    if auto_mode and display_text:
                        streamed = self._emit_chat(display_text)

                    match = re.search(r"<cmd>\s*([\s\S]*?)\s*</cmd>", answer, re.IGNORECASE)
                    if match:
                        exec_cmd = match.group(1).strip()
                        if auto_mode:
                            return self._execute_with_followup(exec_cmd, preface=display_text or None)
                        self.state.pending_command = exec_cmd
                        return self._format_confirmation_prompt(answer, exec_cmd)

                    colors = getattr(self.state, "colors_enabled", True)
                    result = color_text(answer, "green", enable=colors) if colors else answer
                    if auto_mode and streamed and getattr(self.state, "last_answer_streamed", False):
                        return ""
                    return result
                except Exception as e:
                    msg = f"LLM provider error: {e}"
                    colors = getattr(self.state, "colors_enabled", True)
                    auto_mode = getattr(self.state, "auto_accept_commands", False)
                    if auto_mode:
                        handled = self._emit_chat(msg, color="red")
                        if handled and getattr(self.state, "last_answer_streamed", False):
                            return ""
                    return color_text(msg, "red", enable=colors) if colors else msg

        return "I'm ready to help. Ask anything about your debug session."

    def summary(self) -> str:
        """Return a concise session summary including debugger, goal, provider, and recent activity."""
        dbg = getattr(self.backend, "name", "debugger")
        provider = getattr(self.state, "selected_provider", "(none)")
        goal = (self.state.goal or "").strip()
        attempts = self.state.attempts[-5:]
        attempts_txt = "\n".join(f"  - {a.cmd}: {a.output_snippet[:120]}" for a in attempts if a.cmd)

        # Parse last few Q/A lines from facts
        qa_lines = [l for l in self.state.facts if l.startswith("Q:") or l.startswith("A:")]
        qa_tail = qa_lines[-6:]  # up to 3 pairs
        qa_txt = "\n".join(f"  {l}" for l in qa_tail)

        last_out = head_tail_truncate(self.state.last_output or "", 400)

        parts = [
            f"Session {self.state.session_id}",
            f"Debugger: {dbg}",
            f"Provider: {provider}",
        ]
        if goal:
            parts.append(f"Goal: {goal}")
        if attempts_txt:
            parts.append("Recent commands:")
            parts.append(attempts_txt)
        if last_out:
            parts.append("Last output:")
            parts.append("  " + last_out.replace("\n", "\n  "))
        if qa_txt:
            parts.append("Recent chat:")
            parts.append(qa_txt)

        return "\n".join(parts)


def _extract_command_like(text: str) -> Optional[str]:
    """Extract a probable GDB command from free-form text.

    Rules:
    - Accept /exec <cmd>
    - Accept quoted/backticked text only if it matches a known GDB command pattern
    - Accept single-word tokens only if they are known GDB commands (e.g., run, continue, bt)
    - Do NOT treat arbitrary code (e.g., assembly like 'movq $0x0, -0x8(%rbp)') as a command
    """
    if not text:
        return None
    # Fenced code blocks: ```[gdb]\n<cmd>\n```
    fence = re.search(r"```(?:gdb)?\s*\n([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        body = fence.group(1)
        for line in body.splitlines():
            cand = line.strip()
            if not cand:
                continue
            if _is_likely_gdb_command(cand):
                return cand
    # /exec <cmd>
    m = re.search(r"/exec\s+([^\n]+)", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        return candidate if _is_likely_gdb_command(candidate) else None
    # backticks or quotes
    m = re.search(r"`([^`]+)`", text)
    if m:
        cand = m.group(1).strip()
        if cand.lower().startswith("gdb> "):
            cand = cand[5:].strip()
        return cand if _is_likely_gdb_command(cand) else None
    m = re.search(r"\"([^\"]+)\"", text)
    if m:
        cand = m.group(1).strip()
        if cand.lower().startswith("gdb> "):
            cand = cand[5:].strip()
        return cand if _is_likely_gdb_command(cand) else None
    m = re.search(r"'([^']+)'", text)
    if m:
        cand = m.group(1).strip()
        if cand.lower().startswith("gdb> "):
            cand = cand[5:].strip()
        return cand if _is_likely_gdb_command(cand) else None
    # As a fallback, scan lines for a likely command suggestion
    for ln in text.splitlines():
        cand = ln.strip()
        if _is_likely_gdb_command(cand):
            return cand
    # common single-word commands
    token = text.strip().split()[0].lower()
    if _is_likely_gdb_command(token):
        return text.strip()
    return None


def _is_explanation_request(text: str) -> bool:
    # Legacy helper (kept for potential future use); no longer used in the LLM-driven flow.
    t = (text or "").lower()
    keywords = [
        "explain", "what does", "what is this doing", "describe", "explanation",
        "in chinese", "translate", "translation", "中文", "解释", "说明",
    ]
    return any(k in t for k in keywords)


def _is_likely_gdb_command(cmd: str) -> bool:
    """Whitelist-style check for typical GDB commands to avoid false positives."""
    if not cmd:
        return False
    c = cmd.strip()
    # Prefix-based checks
    allowed_prefixes = (
        "run", "r", "continue", "c", "next", "n", "step", "s", "finish", "start",
        "bt", "backtrace", "where", "frame", "f", "up", "down",
        "info", "break", "tbreak", "watch", "rwatch", "awatch", "delete", "enable", "disable",
        "disassemble", "x/", "x ", "list", "print", "p ", "set ", "thread", "inferior",
        "select-frame", "layout", "starti", "file ",
    )
    if any(c.startswith(p) for p in allowed_prefixes):
        return True
    # Common exact singles
    if c in {"run", "r", "continue", "c", "bt", "where", "start"}:
        return True
    return False


def _wants_chinese(text: str) -> bool:
    t = (text or "").lower()
    # Detect explicit requests and presence of CJK characters
    if any(k in t for k in ["in chinese", "中文", "用中文", "中文回答", "请用中文", "中文解释"]):
        return True
    try:
        import re as _re
        return _re.search(r"[\u4e00-\u9fff]", text) is not None
    except Exception:
        return False


# Intentionally do not interpret user confirmations locally; the LLM will
# decide when to emit <cmd>...</cmd> after user confirmation per the prompt.


def _extract_commands_list(text: str) -> List[str]:
    """Extract a small list of GDB commands from assistant text.

    Supports:
    - ```gdb\n<cmd>\n<cmd>\n```
    - Lines beginning with 'gdb> '
    - A single line with ';' separated commands
    """
    if not text:
        return []
    cmds: List[str] = []
    # Fenced gdb block
    fence = re.search(r"```gdb\s*\n([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        body = fence.group(1)
        for ln in body.splitlines():
            line = ln.strip()
            if not line:
                continue
            if line.lower().startswith("gdb> "):
                line = line[5:].strip()
            if _is_likely_gdb_command(line):
                cmds.append(line)
        return cmds
    # Lines starting with gdb>
    for ln in text.splitlines():
        line = ln.strip()
        if line.lower().startswith("gdb> "):
            cand = line[5:].strip()
            if _is_likely_gdb_command(cand):
                cmds.append(cand)
    if cmds:
        return cmds
    # Inline backticks containing commands, possibly multiple
    backticked = re.findall(r"`([^`]+)`", text)
    for seg in backticked:
        cand = seg.strip()
        if cand.lower().startswith("gdb> "):
            cand = cand[5:].strip()
        # split on ';' or newlines if the segment has multiple
        parts = [p.strip() for p in re.split(r"[;\n]+", cand) if p.strip()]
        for p in parts:
            if _is_likely_gdb_command(p):
                cmds.append(p)
    if cmds:
        return cmds
    # Single-line semi-colon separated inline proposal
    inline = _extract_command_like(text)
    if inline:
        parts = [p.strip() for p in re.split(r"[;\n]+", inline) if p.strip()]
        return [p for p in parts if _is_likely_gdb_command(p)]
    return []


def _format_confirmation_message(cmds: List[str], colors: bool = True) -> str:
    echo_lines = [f"gdb> {c}" for c in cmds]
    if colors:
        echo_lines = [color_text(l, "cyan", bold=True, enable=True) for l in echo_lines]
    body = "\n".join(echo_lines)
    return f"I plan to run:\n{body}\nConfirm? (yes/no)"


def _prefix_dbg_echo(cmd: str, label: str = "gdb", colors: bool = True) -> str:
    line = f"{label}> {cmd}"
    return color_text(line, "cyan", bold=True, enable=True) if colors else line


def _call_llm(provider_name: str, question: str, state: SessionState) -> str:
    prov = providers.get_provider(provider_name)
    if provider_name == "openrouter":
        from dbgcopilot.llm import openrouter as _or
        ask_fn = _or.create_provider(session_config=state.config)
        return ask_fn(question)
    if provider_name in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "llama-cpp", "modelscope"}:
        from dbgcopilot.llm import openai_compat as _oa
        ask_fn = _oa.create_provider(session_config=state.config, name=provider_name)
        return ask_fn(question)
    return prov.ask(question) if prov else ""


def _execute_and_format(backend: Any, cmd: str, colors: bool) -> str:
    try:
        out = backend.run_command(cmd)
        label = getattr(backend, "name", "debugger") or "debugger"
        echoed = _prefix_dbg_echo(cmd, label=label, colors=colors)
        full = f"{echoed}\n{out}" if out else echoed
        return full
    except Exception as e:
        return f"Error running '{cmd}': {e}"


def _llm_summarize_session(self: "CopilotOrchestrator") -> str:
    """Ask the LLM for a concise session summary using trimmed, high-signal context.

    Returns plain text. Falls back to local summary on provider errors.
    """
    goal = (self.state.goal or "").strip()
    attempts = self.state.attempts[-5:]
    attempts_txt = "\n".join(
        f"- {a.cmd}: {a.output_snippet}" for a in attempts if getattr(a, "output_snippet", "")
    )
    last_out = head_tail_truncate(self.state.last_output or "", 1200)
    # Use only the last ~40 chat lines to avoid bloat
    chat_tail = self.state.chatlog[-40:]
    chat_txt = "\n".join(chat_tail)
    # Build a compact prompt for summarization
    prompt = (
        "You are a helpful debugging assistant. Produce a concise summary of the session below.\n"
        "Keep it to 5-8 bullet points, plus one short suggested next step if relevant.\n"
        "Do NOT include any preamble or extra text; output only the summary text.\n\n"
        + (f"Goal: {goal}\n" if goal else "")
        + (f"Recent commands and snippets:\n{attempts_txt}\n" if attempts_txt else "")
        + (f"Last output (truncated):\n{last_out}\n" if last_out else "")
        + (f"Recent chat (tail):\n{chat_txt}\n" if chat_txt else "")
        + "\nSummary:"
    )
    pname = getattr(self.state, "selected_provider", None) or self.state.config.get("llm_provider")
    if pname:
        try:
            return _call_llm(pname, prompt, self.state)
        except Exception:
            pass
    # Fallback to local summary
    return self.summary()


def _execute_once(self: "CopilotOrchestrator", exec_cmd: str) -> tuple[str, bool]:
    """Execute a single command and return its output along with streaming status."""
    colors = getattr(self.state, "colors_enabled", True)
    out = _execute_and_format(self.backend, exec_cmd, colors=colors)
    self.state.last_output = out
    self.state.attempts.append(Attempt(cmd=exec_cmd, output_snippet=(out or "")[:160]))
    self.state.chatlog.append(f"Assistant: (executed) {exec_cmd}\n" + (out or ""))
    streamed = False
    sink = getattr(self.state, "debugger_output_sink", None)
    if sink:
        try:
            sink(out)
            streamed = True
        except Exception:
            streamed = False
    if out:
        if not streamed:
            self.state.pending_outputs.append(out)
        self.state.facts.append(f"O: {out.splitlines()[0]}")
    return out, streamed



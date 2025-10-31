"""Interactive orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
from __future__ import annotations

from typing import Optional, List
import re
from dbgcopilot.core.state import Attempt
from dbgcopilot.llm import providers
from dbgcopilot.utils.io import head_tail_truncate, color_text
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

    def __init__(self, backend, state):
        self.backend = backend
        self.state = state
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

    def _load_prompt_config(self) -> dict:
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
        return f"[copilot] Prompts reloaded from {self.prompt_source}."

    def get_prompt_config(self) -> dict:
        d = dict(self.prompt_config)
        d["_source"] = self.prompt_source
        return d

    def ask(self, question: str) -> str:
        """LLM-driven with human-in-the-loop confirmations.

        Contract:
        - The LLM proposes commands and asks for confirmation without <cmd>.
        - After the user confirms, the LLM replies with ONLY <cmd>...</cmd>. We execute it once and return the output.
        - We do not parse yes/no locally for command confirmations; the LLM decides when to emit <cmd>.

        Safety/limits: If context is too large, we prompt for 'summarize and new session' or 'new session'.
        Output: Either assistant guidance or executed command output (with debugger> echo).
        """
        text = (question or "").strip()

        # Sanitize any legacy bad entries in attempts from previous versions
        if any(a is None or not isinstance(a, Attempt) for a in self.state.attempts):
            self.state.attempts = [a for a in self.state.attempts if isinstance(a, Attempt)]

        # Build full transcript as conversation history
        dbg = getattr(self.backend, "name", "debugger")
        goal = (self.state.goal or "").strip()

        session_cfg = {
            "provider": self.state.provider_name,
            "model": self.state.model_override,
            "api_key": self.state.provider_api_key,
        }

        # Prepare conversation lines: all previous chat plus the new user message
        prev_lines = list(self.state.chatlog)
        prev_lines.append(f"User: {text}")

        # Simple context size guard (character-based)
        # Threshold chosen conservatively; providers will have token limits, this is a rough pre-check.
        MAX_CONTEXT_CHARS = int(self.prompt_config.get("max_context_chars", 16000))
        transcript_for_llm = "\n".join(prev_lines)
        if len(transcript_for_llm) > MAX_CONTEXT_CHARS:
            # Allow two exact control phrases to break the overflow loop without using the LLM.
            choice = (text or "").strip().lower()
            if choice in {"summarize and new session", "summarise and new session"}:
                # Prefer an LLM-generated concise summary using a trimmed context; fallback to local summary.
                try:
                    prev_summary = _llm_summarize_session(self)
                except Exception:
                    prev_summary = self.summary()
                try:
                    import uuid as _uuid
                    self.state.session_id = str(_uuid.uuid4())[:8]
                except Exception:
                    pass
                # Clear heavy history
                self.state.chatlog.clear()
                self.state.attempts.clear()
                self.state.facts.clear()
                self.state.last_output = ""
                # Seed new session with the summary as a fact for future context
                if prev_summary:
                    self.state.facts.append(f"Summary: {prev_summary.splitlines()[0][:160]}")
                return (
                    f"[copilot] Started a new session: {self.state.session_id}\n"
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
                return f"[copilot] Started a fresh session: {self.state.session_id}"
            # Otherwise, display the prompt without appending to chat (to avoid growing context further).
            return (
                "[copilot] Your session context is quite large. Would you like me to summarize the "
                "current session and start a new one from that summary, or start a fresh session "
                "without a summary? Reply with 'summarize and new session' or 'new session'."
            )

        # A small context block with high-signal items we still pass along explicitly
        # (Some LLMs benefit from repeated short context fields.)
        attempts = [a for a in self.state.attempts[-5:] if isinstance(a, Attempt)]
        attempts_txt = "\n".join(
            f"- {a.cmd}: {a.output_snippet}" for a in attempts if getattr(a, "output_snippet", "")
        )
        last_out = head_tail_truncate(self.state.last_output or "", 2000)
        goal = (self.state.goal or "").strip()

        # Language preference
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

        # Use selected provider from state if available
        pname = getattr(self.state, "selected_provider", None) or self.state.config.get("llm_provider")
        if pname:
            prov = providers.get_provider(pname)
            if prov:
                try:
                    # Providers that need a session-bound instance
                    if pname == "openrouter":
                        from dbgcopilot.llm import openrouter as _or
                        ask_fn = _or.create_provider(session_config=self.state.config)
                        answer = ask_fn(primed_question)
                    elif pname in {"openai-http", "ollama", "deepseek", "qwen", "kimi", "glm", "llama-cpp", "modelscope"}:
                        from dbgcopilot.llm import openai_compat as _oa
                        ask_fn = _oa.create_provider(session_config=self.state.config, name=pname)
                        answer = ask_fn(primed_question)
                    else:
                        answer = prov.ask(primed_question)

                    # Record raw exchange
                    self.state.chatlog.append(f"User: {question.strip()}")
                    self.state.chatlog.append(f"Assistant: {answer.strip()}")
                    self.state.facts.append(f"Q: {question.strip()}")
                    self.state.facts.append(f"A: {(answer.splitlines()[0] if answer else '').strip()}")

                    # If the assistant returned a <cmd>...</cmd>, execute it.
                    m = re.search(r"<cmd>\s*([\s\S]*?)\s*</cmd>", answer, re.IGNORECASE)
                    if m:
                        exec_cmd = m.group(1).strip()
                        return _execute_once(self, exec_cmd)

                    # Otherwise return assistant message as-is
                    return color_text(answer, "green", enable=True) if getattr(self.state, "colors_enabled", True) else answer
                except Exception as e:
                    msg = f"[copilot] LLM provider error: {e}"
                    if getattr(self.state, "colors_enabled", True):
                        return color_text(msg, "red", enable=True)
                    return msg

        # fallback placeholder
        return (
            "[copilot] (placeholder) I'm ready to help. Ask anything about your debug session."
        )

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
            f"[copilot] Session {self.state.session_id}",
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
    return f"[copilot] I plan to run:\n{body}\nConfirm? (yes/no)"


def _prefix_dbg_echo(cmd: str, label: str = "gdb", colors: bool = True) -> str:
    line = f"{label}> {cmd}"
    return color_text(line, "cyan", bold=True, enable=True) if colors else line


def _call_llm(provider_name: str, question: str, state) -> str:
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


def _execute_and_format(backend, cmd: str, colors: bool) -> str:
    try:
        out = backend.run_command(cmd)
        label = getattr(backend, "name", "debugger") or "debugger"
        echoed = _prefix_dbg_echo(cmd, label=label, colors=colors)
        full = f"{echoed}\n{out}" if out else echoed
        return full
    except Exception as e:
        return f"[copilot] Error running '{cmd}': {e}"


def _llm_summarize_session(self) -> str:
        """Ask the LLM for a concise session summary using trimmed, high-signal context.

        Returns plain text. Falls back to local summary on provider errors.
        """
        dbg = getattr(self.backend, "name", "debugger")
        goal = (self.state.goal or "").strip()
        attempts = [a for a in self.state.attempts[-5:] if isinstance(a, Attempt)]
        attempts_txt = "\n".join(f"- {a.cmd}: {a.output_snippet}" for a in attempts if getattr(a, "output_snippet", ""))
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


def _execute_once(self, exec_cmd: str) -> str:
    """Execute a single command and return its output."""
    colors = getattr(self.state, "colors_enabled", True)
    out = _execute_and_format(self.backend, exec_cmd, colors=colors)
    self.state.last_output = out
    self.state.attempts.append(Attempt(cmd=exec_cmd, output_snippet=(out or "")[:160]))
    self.state.chatlog.append(f"Assistant: (executed) {exec_cmd}\n" + (out or ""))
    if out:
        self.state.facts.append(f"O: {out.splitlines()[0]}")
    return out



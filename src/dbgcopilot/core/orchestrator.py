"""Agent orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
from __future__ import annotations

from typing import Optional
import re
from dbgcopilot.core.state import Attempt
from dbgcopilot.llm import providers
from dbgcopilot.utils.io import head_tail_truncate


class AgentOrchestrator:
    """Placeholder orchestrator.

    In future iterations, this will:
    - Initialize LLM and prompt templates
    - Provide methods for suggest/ask/plan/auto/report
    - Use a Backend to run commands safely
    """

    def __init__(self, backend, state):
        self.backend = backend
        self.state = state

    def ask(self, question: str) -> str:
        """Ask the selected LLM with lightweight context priming and confirmation flow.

        Contract:
        - Input: natural language question or a short reply like 'yes', 'y', 'no', 'n', or an alternative debugger command.
        - Behavior: If a pending command exists in state and user replies yes/y -> execute it. If no/n -> do not execute and clear pending.
          If user provides an alternative command (e.g., 'run' or 'continue' or 'r'), set pending to that command and ask for confirmation.
        - Otherwise: Ask LLM for guidance; if the LLM appears to suggest a concrete debugger command, set pending and ask for yes/no confirmation with the exact command string.
        - Output: A concise assistant string; if execution occurs, append the command output to the response and record in state.
        """
        text = (question or "").strip()

        # Sanitize any legacy bad entries in attempts from previous versions
        if any(a is None or not isinstance(a, Attempt) for a in self.state.attempts):
            self.state.attempts = [a for a in self.state.attempts if isinstance(a, Attempt)]

        # 1) Handle confirmation replies when a command is pending
        if self.state.pending_cmd:
            # Only accept 'yes'/'y' to confirm our own pending command
            if text.lower() in {"yes", "y"}:
                cmd = self.state.pending_cmd
                self.state.pending_cmd = None
                try:
                    out = self.backend.run_command(cmd)
                    self.state.last_output = out
                except Exception as e:
                    out = f"[copilot] Error running '{cmd}': {e}"
                # Record attempt properly
                self.state.attempts.append(Attempt(cmd=cmd, output_snippet=(out or "")[:160]))
                self.state.chatlog.append(f"User: {text}")
                self.state.chatlog.append("Assistant: ok\n" + (out or ""))
                # Also record the top line of output as a fact for downstream context
                if out:
                    first = out.splitlines()[0]
                    self.state.facts.append(f"O: {first}")
                return "ok\n" + (out or "")
            if text.lower() in {"no", "n"}:
                prev = self.state.pending_cmd
                self.state.pending_cmd = None
                self.state.chatlog.append(f"User: {text}")
                self.state.chatlog.append("Assistant: Cancelled. You can suggest another command, e.g. 'run' or '/exec <cmd>'.")
                return f"Cancelled. I won't run '{prev}'. Tell me another command, or say what you'd like to try."
            # Interpret short alt commands while pending (e.g., 'run', 'continue', 'c', 'bt')
            alt = _extract_command_like(text)
            if alt:
                self.state.pending_cmd = alt
                self.state.chatlog.append(f"User: {text}")
                prompt = f"I will use the command '{alt}'. Please confirm with yes/y, or say no to cancel."
                self.state.chatlog.append(f"Assistant: {prompt}")
                return prompt

        # 2) No pending: try to interpret direct command requests like 'run the program'
        explaining = _is_explanation_request(text)
        direct = None if explaining else _infer_direct_command(text)
        if direct:
            self.state.pending_cmd = direct
            prompt = f"I will use the command '{direct}' to proceed. Please confirm with yes/y, or say no to cancel or suggest another command."
            self.state.chatlog.append(f"User: {text}")
            self.state.chatlog.append(f"Assistant: {prompt}")
            return prompt

        # 3) Otherwise, call the LLM and then try to extract a suggested command
        # Build lightweight context so the LLM knows we're inside a debugger session
        dbg = getattr(self.backend, "name", "debugger")
        attempts = [a for a in self.state.attempts[-5:] if isinstance(a, Attempt)]  # recent history only
        attempts_txt = "\n".join(
            f"- {a.cmd}: {a.output_snippet}" for a in attempts if getattr(a, "output_snippet", "")
        )
        last_out = head_tail_truncate(self.state.last_output or "", 2000)
        goal = (self.state.goal or "").strip()

        # Language preference
        wants_zh = _wants_chinese(question)

        system_preamble = (
            f"You are a debugging copilot inside {dbg}.\n"
            "Follow these rules concisely: \n"
            "- Prefer small, low-risk diagnostic commands first.\n"
            "- Never fabricate output; quote exact snippets from tool results.\n"
            "- Ask for confirmation before state-changing actions.\n"
            "- When the user asks for code or listings, suggest the exact debugger command to show it.\n"
            "- If the user references a symbol like 'main', infer they likely mean the function/frame in the current context.\n"
            "- If the user requests a specific language, respond in that language.\n"
        )

        context_block = (
            (f"Goal: {goal}\n" if goal else "")
            + (f"Recent commands and snippets:\n{attempts_txt}\n" if attempts_txt else "")
            + (f"Last output:\n{last_out}\n" if last_out else "")
        )

        lang_hint = ("Please answer in Simplified Chinese (中文).\n" if wants_zh else "")

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
                    # For OpenRouter, allow model override via session config
                    if pname == "openrouter":
                        from dbgcopilot.llm import openrouter as _or
                        ask_fn = _or.create_provider(session_config=self.state.config)
                        answer = ask_fn(primed_question)
                    else:
                        answer = prov.ask(primed_question)
                    # Try to extract a concrete command from the LLM answer
                    suggested = None if explaining else _extract_command_like(answer)
                    if suggested:
                        self.state.pending_cmd = suggested
                        answer = (
                            f"I will use the command '{suggested}' to proceed. "
                            "Please confirm with yes/y, or say no to cancel or suggest another command.\n\n"
                            f"Model suggestion:\n{answer}"
                        )
                    # Record transcript and brief facts
                    self.state.chatlog.append(f"User: {question.strip()}")
                    self.state.chatlog.append(f"Assistant: {answer.strip()}")
                    self.state.facts.append(f"Q: {question.strip()}")
                    self.state.facts.append(f"A: {(answer.splitlines()[0] if answer else '').strip()}")
                    return answer
                except Exception as e:
                    return f"[copilot] LLM provider error: {e}"

        # fallback placeholder
        return (
            "[copilot] (placeholder) I would likely start with 'bt' to inspect the stack.\n"
            "Would you like me to execute 'bt'? (y/N)"
        )


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
        return cand if _is_likely_gdb_command(cand) else None
    m = re.search(r"\"([^\"]+)\"", text)
    if m:
        cand = m.group(1).strip()
        return cand if _is_likely_gdb_command(cand) else None
    m = re.search(r"'([^']+)'", text)
    if m:
        cand = m.group(1).strip()
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


def _infer_direct_command(user_text: str) -> Optional[str]:
    """Map common natural requests to debugger commands.

    Examples:
    - 'run the program' -> 'run'
    - 'please continue' -> 'continue'
    """
    t = user_text.lower()
    # Start a specific program path: e.g., "start the program examples/crash_demo/crash"
    m = re.search(r"(?:run|start)(?:\s+the\s+program)?\s+([./\w\-]+(?:/[./\w\-]+)*)", user_text, re.IGNORECASE)
    if m:
        path = m.group(1)
        # Produce a sequence: set file <path>; run
        return f"file {path}; run"
    if any(p in t for p in ["run the program", "pls run", "please run", "start running", "start the program"]):
        return "run"
    if any(p in t for p in ["continue", "resume", "carry on"]):
        return "continue"
    # Set breakpoint intents
    if "breakpoint" in t or t.startswith("break ") or " set break" in t:
        # Try to find a target after 'at ' or after 'break '
        m = re.search(r"break(?:point)?\s+(?:at\s+)?([\w:\./+\-]+)", t)
        if not m:
            m = re.search(r"at\s+([\w:\./+\-]+)", t)
        if m:
            target = m.group(1)
            return f"break {target}"
    return None


def _is_explanation_request(text: str) -> bool:
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

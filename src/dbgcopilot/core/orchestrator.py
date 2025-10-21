"""Agent orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
from __future__ import annotations

from typing import Optional
import re
from dbgcopilot.core.state import Attempt
from dbgcopilot.llm import providers
from dbgcopilot.utils.io import head_tail_truncate, color_text
from pathlib import Path
import os
import json
from dbgcopilot.prompts.defaults import DEFAULT_PROMPT_CONFIG


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
        """Always call the LLM with full session context and follow its <cmd> directive.

        New contract (LLM-driven):
        - Input: any natural language from the user (questions, confirmations, or instructions).
        - Behavior: Orchestrator always sends the full prior chat transcript and prior debugging outputs
          to the LLM with clear instructions. If the LLM replies with <cmd>...</cmd>, we execute that
          command in the debugger and return the command output. Otherwise we return the LLM's reply.
        - Safety/limits: If the composed context exceeds a simple character threshold, return a warning
          prompting the user to summarize and start a new session (or start fresh) instead of calling the LLM.
        - Output: Either the debugger command output when <cmd> is provided, or the assistant reply text.
        """
        text = (question or "").strip()

        # Sanitize any legacy bad entries in attempts from previous versions
        if any(a is None or not isinstance(a, Attempt) for a in self.state.attempts):
            self.state.attempts = [a for a in self.state.attempts if isinstance(a, Attempt)]

        # Build full transcript as conversation history
        dbg = getattr(self.backend, "name", "debugger")
        goal = (self.state.goal or "").strip()

        # Prepare conversation lines: all previous chat plus the new user message
        prev_lines = list(self.state.chatlog)
        prev_lines.append(f"User: {text}")

        # Simple context size guard (character-based)
        # Threshold chosen conservatively; providers will have token limits, this is a rough pre-check.
        MAX_CONTEXT_CHARS = int(self.prompt_config.get("max_context_chars", 16000))
        transcript_for_llm = "\n".join(prev_lines)
        if len(transcript_for_llm) > MAX_CONTEXT_CHARS:
            warning = (
                "[copilot] Your session context is quite large. Would you like me to summarize the "
                "current session and start a new one from that summary, or start a fresh session "
                "without a summary? Reply with 'summarize and new session' or 'new session'."
            )
            # Record the prompt to the chatlog
            self.state.chatlog.append(f"Assistant: {warning}")
            return warning

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

        rules_lines = "\n".join(f"- {r}" for r in self.prompt_config.get("rules", []))
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
                    # For OpenRouter, allow model override via session config
                    if pname == "openrouter":
                        from dbgcopilot.llm import openrouter as _or
                        ask_fn = _or.create_provider(session_config=self.state.config)
                        answer = ask_fn(primed_question)
                    else:
                        answer = prov.ask(primed_question)

                    # Record the raw assistant reply first
                    self.state.chatlog.append(f"User: {question.strip()}")
                    # Store uncolored in chatlog for clean logs
                    self.state.chatlog.append(f"Assistant: {answer.strip()}")
                    self.state.facts.append(f"Q: {question.strip()}")
                    self.state.facts.append(f"A: {(answer.splitlines()[0] if answer else '').strip()}")

                    # If the assistant returned a <cmd>...</cmd>, execute it and return the output
                    m = re.search(r"<cmd>\s*([\s\S]*?)\s*</cmd>", answer, re.IGNORECASE)
                    if m:
                        cmd = m.group(1).strip()
                        try:
                            # Prepend an echo of the command for better UX parity with typing in GDB
                            echoed = f"{cmd}\n"
                            out = self.backend.run_command(cmd)
                            if out:
                                out = echoed + out
                            else:
                                out = echoed
                            self.state.last_output = out
                        except Exception as e:
                            out = f"[copilot] Error running '{cmd}': {e}"
                        # Record attempt and output in chatlog
                        self.state.attempts.append(Attempt(cmd=cmd, output_snippet=(out or "")[:160]))
                        # Include a clear execution marker in chat for full-context future turns
                        self.state.chatlog.append(f"Assistant: (executed) {cmd}\n" + (out or ""))
                        # Record top line as a fact
                        if out:
                            first = out.splitlines()[0]
                            self.state.facts.append(f"O: {first}")
                        # Colorize full output when returning to REPL
                        if getattr(self.state, "colors_enabled", True):
                            # Command echo cyan, output default
                            lines = (out or "").splitlines()
                            if lines:
                                lines[0] = color_text(lines[0], "cyan", bold=True, enable=True)
                            return "\n".join(lines)
                        return out or ""

                    # No command tag -> return assistant message as-is
                    if getattr(self.state, "colors_enabled", True):
                        return color_text(answer, "green", enable=True)
                    return answer
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



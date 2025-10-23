"""LLDB subprocess backend using pexpect.

Spawns an interactive `lldb` process and drives it via a pseudo-tty.
Used by the standalone copilot> REPL outside of LLDB.
"""
from __future__ import annotations

from typing import Optional, List
import re

try:
    import pexpect
except Exception:
    pexpect = None  # type: ignore


class LldbSubprocessBackend:
    name = "lldb"

    def __init__(self, lldb_path: str = "lldb", timeout: float = 10.0, prompt: str = "dbgcopilot>") -> None:
        self.lldb_path = lldb_path
        self.timeout = timeout
        self.prompt = prompt
        self.child: Optional[pexpect.spawn] = None  # type: ignore
        self._default_prompt_re = re.compile(r"\(lldb\)\s", re.MULTILINE)
        self._prompt_re: Optional[re.Pattern[str]] = None

    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is not available; cannot start subprocess backend")
        # Launch LLDB. Use encoding for string I/O.
        self.child = pexpect.spawn(self.lldb_path, [], encoding="utf-8", timeout=self.timeout)
        # Immediately set a simple prompt we can match reliably, then expect it
        try:
            # Disable colors for cleaner capture and set a simple prompt we can regex reliably
            self.child.sendline("settings set use-color false")
            self.child.sendline(f"settings set prompt {self.prompt} ")
        except Exception:
            pass
        # Use custom prompt pattern for subsequent expects
        ansi = r"(?:\x1b\[[0-9;]*m)*"
        self._prompt_re = re.compile(ansi + re.escape(self.prompt) + ansi + r"\s*")
        try:
            self._expect_prompt()
        except Exception:
            # Nudge with a newline and try again
            try:
                self.child.sendline("")
                self._expect_prompt()
            except Exception:
                pass
        # Configure non-interactive friendly behavior (after prompt is set)
        try:
            self._send_and_capture("settings set auto-confirm true")
        except Exception:
            pass

    def _expect_prompt(self) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not running")
        # Expect the custom prompt if available, else fallback to default
        pat = self._prompt_re or self._default_prompt_re
        self.child.expect(pat)
        return self.child.before or ""

    def _send_and_capture_raw(self, cmd: str, timeout: Optional[float] = None) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not running")
        self.child.sendline(cmd)
        old_timeout = self.child.timeout
        if timeout is not None:
            self.child.timeout = timeout
        try:
            self._expect_prompt()
            out = self.child.before or ""
        finally:
            self.child.timeout = old_timeout
        return out

    def _send_and_capture(self, cmd: str, timeout: Optional[float] = None) -> str:
        # Wrap raw capture and remove any echoed command line
        out = self._send_and_capture_raw(cmd, timeout=timeout)
        text = out.lstrip("\r\n")
        lines = text.splitlines()
        if lines and lines[0].strip() == cmd.strip():
            lines = lines[1:]
        return "\n".join(lines)

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not initialized; call initialize_session()")
        parts: List[str] = []
        for chunk in (cmd or "").replace("\r", "\n").split("\n"):
            parts.extend([p.strip() for p in chunk.split(";") if p.strip()])
        if not parts:
            parts = [cmd.strip()]

        outputs: List[str] = []
        for part in parts:
            try:
                out = self._send_and_capture(part, timeout=timeout)
            except pexpect.TIMEOUT as e:  # type: ignore[attr-defined]
                outputs.append(f"[lldb timeout] {part}: {e}")
                continue
            except pexpect.EOF as e:  # type: ignore[attr-defined]
                outputs.append(f"[lldb eof] {part}: {e}")
                break
            except Exception as e:
                outputs.append(f"[lldb error] {part}: {e}")
                continue
            outputs.append(out.replace("\r\n", "\n"))
        return "\n".join(o for o in outputs if o)

    def __del__(self):  # pragma: no cover
        try:
            if self.child and self.child.isalive():
                try:
                    self.child.sendline("quit")
                    self.child.expect(pexpect.EOF, timeout=1)  # type: ignore[arg-type]
                except Exception:
                    self.child.close(force=True)
        except Exception:
            pass

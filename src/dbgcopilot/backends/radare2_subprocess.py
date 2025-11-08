"""Radare2 subprocess backend using pexpect.

Spawns an interactive `radare2` session and relays commands via a
pseudo-tty. The backend requires a program path up-front so r2 can open
and analyze the binary.
"""
from __future__ import annotations

from typing import Optional, List, Any
import os
import re

try:
    import pexpect  # type: ignore
except Exception:  # pragma: no cover - import error surfaced at runtime
    pexpect = None  # type: ignore


class Radare2SubprocessBackend:
    """Minimal radare2 CLI wrapper via pexpect."""

    name = "radare2"
    _EXIT_COMMANDS = {"quit", "q", "exit"}

    def __init__(
        self,
        program: str,
        *,
        r2_path: str = "radare2",
        timeout: float = 20.0,
        working_dir: Optional[str] = None,
    ) -> None:
        if not program:
            raise ValueError("Radare2 backend requires a program path")
        self.r2_path = r2_path
        self.program = program
        self.timeout = timeout
        self.working_dir = working_dir or os.getcwd()
        self.child: Optional[Any] = None
        self.prompt = "dbg> "
        self._prompt_re = re.compile(re.escape(self.prompt))
        self._startup_output: str = ""

    @property
    def startup_output(self) -> str:
        return self._startup_output

    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is required to use the radare2 backend")
        env = dict(os.environ)
        env["R2PROMPT"] = self.prompt
        args = ["-q", self.program]
        self.child = pexpect.spawn(
            self.r2_path,
            args,
            cwd=self.working_dir,
            env=env,
            encoding="utf-8",
            timeout=self.timeout,
        )
        banner = self._expect_prompt()
        self._startup_output = banner.strip()

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        if self.child is None:
            raise RuntimeError("radare2 subprocess is not initialized; call initialize_session()")
        text = (cmd or "").strip()
        if not text:
            return ""

        outputs: List[str] = []
        for part in self._split_commands(text):
            lower = part.lower()
            if lower in self._EXIT_COMMANDS:
                outputs.append(self._handle_exit(part))
                break
            try:
                out = self._send_and_capture(part, timeout=timeout)
            except Exception as exc:
                outputs.append(f"[radare2 error] {part}: {exc}")
                continue
            outputs.append(out)
        return "\n".join(chunk for chunk in outputs if chunk)

    # Helpers ----------------------------------------------------------
    def _split_commands(self, text: str) -> List[str]:
        pieces: List[str] = []
        for segment in text.replace("\r", "\n").split("\n"):
            pieces.extend([p.strip() for p in segment.split(";") if p.strip()])
        return pieces or [text]

    def _expect_prompt(self) -> str:
        if self.child is None:
            raise RuntimeError("radare2 subprocess is not running")
        self.child.expect(self._prompt_re)
        return self.child.before or ""

    def _send_and_capture(self, cmd: str, timeout: Optional[float] = None) -> str:
        if self.child is None:
            raise RuntimeError("radare2 subprocess is not running")
        child: Any = self.child
        child.sendline(cmd)
        old_timeout = child.timeout
        if timeout is not None:
            child.timeout = timeout
        try:
            child.expect(self._prompt_re)
            out = child.before or ""
        finally:
            child.timeout = old_timeout
        cleaned = out.lstrip("\r\n")
        lines = cleaned.splitlines()
        if lines and lines[0].strip() == cmd.strip():
            lines = lines[1:]
        return "\n".join(lines)

    def _handle_exit(self, cmd: str) -> str:
        if self.child is None:
            return "[radare2 closed] session already terminated"
        child: Any = self.child
        try:
            child.sendline(cmd)
            try:
                child.expect(pexpect.EOF, timeout=self.timeout)  # type: ignore[arg-type]
            except Exception:
                pass
        finally:
            try:
                child.close(force=True)
            except Exception:
                pass
            self.child = None
        try:
            self.initialize_session()
        except Exception as exc:  # pragma: no cover - restart best-effort
            return f"[radare2 closed] {cmd}: {exc}"
        return "[radare2] session restarted; ready for commands"

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            if self.child and self.child.isalive():
                try:
                    self.child.sendline("q")
                    self.child.expect(pexpect.EOF, timeout=1)  # type: ignore[arg-type]
                except Exception:
                    self.child.close(force=True)
        except Exception:
            pass
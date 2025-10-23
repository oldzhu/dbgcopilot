"""GDB subprocess backend using pexpect.

Spawns an interactive `gdb -q` process and drives it via a pseudo-tty.
Suitable for the standalone copilot> REPL where we're outside of GDB.
"""
from __future__ import annotations

from typing import Optional, List
import re

try:
    import pexpect
except Exception as _e:  # pragma: no cover - import error surfaced at runtime
    pexpect = None  # type: ignore


class GdbSubprocessBackend:
    name = "gdb"

    def __init__(self, gdb_path: str = "gdb", timeout: float = 10.0) -> None:
        self.gdb_path = gdb_path
        self.timeout = timeout
        self.child: Optional[pexpect.spawn] = None  # type: ignore
        # Default GDB prompt ends with "(gdb) "; match leniently with optional spaces
        self._prompt_re = re.compile(r"\(gdb\)\s", re.MULTILINE)

    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is not available; cannot start subprocess backend")
        # Spawn gdb quietly; use encoding for str I/O
        self.child = pexpect.spawn(self.gdb_path, ["-q"], encoding="utf-8", timeout=self.timeout)
        # Consume banner until prompt
        self._expect_prompt()
        # Configure GDB for non-interactive usage
        init_cmds = [
            "set pagination off",
            "set height 0",
            "set width 0",
            # Avoid blocking confirmations in non-interactive sessions
            "set confirm off",
        ]
        # Debuginfod can prompt; try to disable if supported
        for c in init_cmds + ["set debuginfod enabled off"]:
            try:
                self._send_and_capture(c)
            except Exception:
                # Ignore failures (older GDB may not support debuginfod setting)
                pass

    # Internal helpers
    def _expect_prompt(self) -> str:
        if not self.child:
            raise RuntimeError("GDB subprocess is not running")
        # Expect either the prompt or EOF/timeout; let exceptions surface for caller
        self.child.expect(self._prompt_re)
        return self.child.before or ""

    def _send_and_capture(self, cmd: str, timeout: Optional[float] = None) -> str:
        if not self.child:
            raise RuntimeError("GDB subprocess is not running")
        # Send command and wait for next prompt; capture output in-between
        self.child.sendline(cmd)
        # Use per-call timeout if provided
        old_timeout = self.child.timeout
        if timeout is not None:
            self.child.timeout = timeout
        try:
            self.child.expect(self._prompt_re)
            out = self.child.before or ""
        finally:
            self.child.timeout = old_timeout
        # Strip a single trailing newline that typically precedes the prompt
        # Also remove echoed command if present as the first line
        text = out.lstrip("\r\n")
        lines = text.splitlines()
        if lines and lines[0].strip() == cmd.strip():
            lines = lines[1:]
        return "\n".join(lines)

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        if not self.child:
            raise RuntimeError("GDB subprocess is not initialized; call initialize_session()")
        # Split multiple commands on newlines and ';'
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
                outputs.append(f"[gdb timeout] {part}: {e}")
                continue
            except pexpect.EOF as e:  # type: ignore[attr-defined]
                outputs.append(f"[gdb eof] {part}: {e}")
                break
            except Exception as e:
                outputs.append(f"[gdb error] {part}: {e}")
                continue
            # Normalize Windows-style newlines just in case
            outputs.append(out.replace("\r\n", "\n"))
        return "\n".join(o for o in outputs if o)

    def __del__(self):  # pragma: no cover - best-effort cleanup
        try:
            if self.child and self.child.isalive():
                # Try a graceful quit without confirmation
                try:
                    self.child.sendline("quit")
                    self.child.expect(pexpect.EOF, timeout=1)  # type: ignore[arg-type]
                except Exception:
                    self.child.close(force=True)
        except Exception:
            pass


"""Python debugging backend driven by the standard-library ``pdb``.

Uses ``python -m pdb`` in a subprocess (via ``pexpect``) so we can interact with the
command-line debugger similarly to the other backends. Commands are intentionally kept
minimal: ``file`` chooses the script, ``run`` starts a fresh pdb session, and common
single-letter shortcuts (``c``, ``n``, ``s``) are supported.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - import guard for optional dependency
    import pexpect  # type: ignore
except Exception:  # pragma: no cover - runtime dependency check
    pexpect = None  # type: ignore


class PythonPdbBackend:
    name = "pdb"
    prompt = "(pydb)"

    _ANSI_PATTERN = r"(?:\x1b\[[0-9;?]*[ -/]*[@-~])*"

    def __init__(
        self,
        program: Optional[str] = None,
        python_path: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.program: Optional[str] = program
        self.python_path = python_path or sys.executable
        self.cwd = cwd
        self.timeout = timeout
        self.child: Optional[Any] = None
        self._prompt_re: Optional[re.Pattern[str]] = None

    # ------------------------------------------------------------------
    # Session lifecycle
    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is required for the Python debugger backend")

    def close(self) -> None:
        if self.child is not None:
            try:
                if self.child.isalive():
                    self.child.terminate(force=True)
            except Exception:
                pass
        self.child = None

    def _prefix(self) -> str:
        return f"[{self.name}]"

    def _compile_prompt_pattern(self, prompt: str) -> re.Pattern[str]:
        prefix = self._ANSI_PATTERN
        # Allow ANSI sequences before and after the literal prompt text.
        pattern = rf"{prefix}{re.escape(prompt)}\s*{prefix}"
        return re.compile(pattern)

    # ------------------------------------------------------------------
    # Command handling
    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        command = (cmd or "").strip()
        if not command:
            return ""

        lower = command.lower()
        if lower.startswith("file "):
            path = command[5:].strip()
            if not path:
                return f"{self._prefix()} provide a script path"
            resolved = self._resolve_program_path(path)
            self.program = resolved
            return f"{self._prefix()} script set to {resolved}"

        if lower in {"run", "r"}:
            return self._handle_run(timeout=timeout)

        if lower in {"quit", "q"}:
            self.close()
            return f"{self._prefix()} session terminated"

        if not self.child or not self.child.isalive():
            return f"{self._prefix()} no active session. Use 'run' first."

        if lower in {"continue", "c"}:
            return self._send_and_capture("continue", timeout=timeout)
        if lower in {"next", "n"}:
            return self._send_and_capture("next", timeout=timeout)
        if lower in {"step", "s", "stepin"}:
            return self._send_and_capture("step", timeout=timeout)
        if lower in {"where", "bt", "backtrace"}:
            return self._send_and_capture("where", timeout=timeout)
        if lower.startswith("print ") or lower.startswith("p "):
            expr = command.split(" ", 1)[1].strip()
            if not expr:
                return f"{self._prefix()} provide an expression"
            return self._send_and_capture(f"p {expr}", timeout=timeout)
        if lower.startswith("info locals"):
            return self._send_and_capture("p locals()", timeout=timeout)

        # Fallback: forward the command verbatim to pdb.
        return self._send_and_capture(command, timeout=timeout)

    # ------------------------------------------------------------------
    # Helpers
    def _resolve_program_path(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            if self.cwd:
                p = Path(self.cwd) / p
            else:
                p = Path.cwd() / p
        return str(p.resolve())

    def _handle_run(self, timeout: float | None = None) -> str:
        if not self.program:
            return f"{self._prefix()} no script configured. Use 'file <script.py>' first."
        self.close()
        assert pexpect is not None  # for type checkers

        cmd = [self.python_path, "-m", "pdb", self.program]
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            self.child = pexpect.spawn(
                cmd[0],
                cmd[1:],
                encoding="utf-8",
                timeout=timeout or self.timeout,
                env=env,  # type: ignore[arg-type]
                cwd=self.cwd or (Path(self.program).parent if self.program else None),
            )
        except FileNotFoundError as exc:
            self.child = None
            return f"{self._prefix()} failed to start python interpreter: {exc}"
        except Exception as exc:
            self.child = None
            return f"{self._prefix()} failed to launch script: {exc}"

        startup = self._expect_initial_prompt()
        if not self.child or not self.child.isalive():
            return startup or f"{self._prefix()} session ended"

        run_output = self._send_and_capture("run", timeout=timeout)
        pieces: list[str] = []
        if startup:
            pieces.append(startup)
        if run_output:
            pieces.append(run_output)
        return "\n".join(piece for piece in pieces if piece)

    def _expect_initial_prompt(self) -> str:
        assert self.child is not None
        assert pexpect is not None
        try:
            self.child.expect(self._compile_prompt_pattern("(Pdb)"))
        except pexpect.EOF:
            message = (self.child.before or "").strip()
            self.child = None
            return message or f"{self._prefix()} process exited before prompt"
        except pexpect.TIMEOUT:
            return f"{self._prefix()} timeout waiting for pdb prompt"
        except Exception as exc:
            return f"{self._prefix()} failed waiting for pdb prompt: {exc}"
        startup = (self.child.before or "").strip()
        # Prime a compiled prompt pattern for later expectations.
        self._prompt_re = self._compile_prompt_pattern("(Pdb)")
        return startup

    def _send_and_capture(self, command: str, timeout: float | None = None) -> str:
        if not self.child or not self.child.isalive():
            return f"{self._prefix()} session ended"
        assert pexpect is not None
        try:
            self.child.sendline(command)
        except Exception as exc:
            return f"{self._prefix()} failed to send command: {exc}"
        prompt_pattern = self._prompt_re or self._compile_prompt_pattern("(Pdb)")
        try:
            self.child.expect(prompt_pattern, timeout=timeout or self.timeout)
            out = self.child.before or ""
            return self._normalize_output(command, out)
        except pexpect.TIMEOUT:
            buffer = self.child.before or ""
            match = prompt_pattern.search(buffer)
            if match:
                captured = buffer[: match.start()]
                return self._normalize_output(command, captured)
            partial = self._normalize_output(command, buffer)
            if partial:
                return f"{partial}\n{self._prefix()} timeout waiting for prompt after '{command}'"
            return f"{self._prefix()} timeout waiting for '{command}'"
        except pexpect.EOF:
            out = self.child.before or ""
            self.child = None
            normalized = self._normalize_output(command, out)
            return normalized or f"{self._prefix()} process exited"

    def _normalize_output(self, command: str, captured: str) -> str:
        text = (captured or "").replace("\r\n", "\n").lstrip("\r\n")
        if text.startswith(command):
            text = text[len(command) :].lstrip()
        return text.strip()

    # ------------------------------------------------------------------
    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass

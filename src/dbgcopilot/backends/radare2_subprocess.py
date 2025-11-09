"""Radare2 backend implemented via r2pipe.

Uses the radare2 pipe API instead of driving an interactive TTY, which avoids
prompt-parsing issues and produces stable command output.
"""
from __future__ import annotations

from typing import Optional, List, Any
import os

from dbgcopilot.utils.io import strip_ansi

try:
    import r2pipe  # type: ignore
except Exception:  # pragma: no cover - import error surfaced at runtime
    r2pipe = None  # type: ignore


class Radare2SubprocessBackend:
    """Radare2 backend that proxies commands via r2pipe."""

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
        self.radare2_path = r2_path
        self.timeout = timeout
        self.working_dir = working_dir or os.getcwd()
        self._startup_output: str = ""
        self._r2: Optional[Any] = None

        if os.path.isabs(program):
            resolved_path = program
        else:
            resolved_path = os.path.join(self.working_dir, program)
        self._program_path = os.path.abspath(resolved_path)

    @property
    def startup_output(self) -> str:
        return self._startup_output

    def initialize_session(self) -> None:
        if r2pipe is None:
            raise RuntimeError("r2pipe is required to use the radare2 backend")

        if not os.path.exists(self._program_path):
            raise RuntimeError(f"radare2 failed to start: binary not found: {self._program_path}")

        prev_cwd: Optional[str] = None
        try:
            if self.working_dir and os.path.isdir(self.working_dir):
                prev_cwd = os.getcwd()
                os.chdir(self.working_dir)

            # Allow callers to override the radare2 binary via environment.
            if self.radare2_path and self.radare2_path != "radare2":
                os.environ["R2PIPE_PATH"] = self.radare2_path

            self._r2 = r2pipe.open(self._program_path)
        except Exception as exc:  # pragma: no cover - initialization path is thin
            raise RuntimeError(self._format_startup_error(exc)) from exc
        finally:
            if prev_cwd is not None:
                os.chdir(prev_cwd)

        self._configure_session()
        self._startup_output = f"radare2 session ready for {os.path.basename(self._program_path)}"

    def run_command(self, cmd: str, timeout: float | None = None) -> str:  # noqa: ARG002 - timeout kept for parity
        if self._r2 is None:
            raise RuntimeError("radare2 session is not initialized; call initialize_session()")

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
                out = self._execute(part)
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

    def _configure_session(self) -> None:
        if self._r2 is None:
            return
        for cmd in (
            "e scr.color=false",
            "e scr.echo=false",
            "e scr.interactive=false",
            "e bin.cache=true",
        ):
            try:
                self._r2.cmd(cmd)
            except Exception:
                pass

    def _execute(self, command: str) -> str:
        if self._r2 is None:
            raise RuntimeError("radare2 session is not running")
        output = self._r2.cmd(command)
        return self._sanitize_output(output)

    def _sanitize_output(self, text: str) -> str:
        cleaned = strip_ansi(text or "")
        cleaned = cleaned.replace("\r", "")
        lines = cleaned.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _format_startup_error(self, exc: Exception) -> str:
        detail = str(exc).strip()
        if detail:
            return f"radare2 failed to start: {detail}"
        return "radare2 failed to start; ensure the binary path is correct and accessible."

    def _handle_exit(self, cmd: str) -> str:
        if self._r2 is None:
            return "[radare2 closed] session already terminated"
        try:
            try:
                self._r2.cmd(cmd)
            finally:
                self._r2.quit()
        except Exception:
            pass
        finally:
            self._r2 = None

        try:
            self.initialize_session()
        except Exception as exc:  # pragma: no cover - restart best-effort
            return f"[radare2 closed] {cmd}: {exc}"
        return "[radare2] session restarted; ready for commands"

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            if self._r2 is not None:
                self._r2.quit()
        except Exception:
            pass
"""Radare2 backend implemented via r2pipe.

Uses the radare2 pipe API instead of driving an interactive TTY, which avoids
prompt-parsing issues and produces stable command output.
"""
from __future__ import annotations

from typing import Optional, List, Any, Tuple
import os
import tempfile

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
        self.prompt = "radare2> "
        self._log_path: Optional[str] = None
        self._log_offset: int = 0

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
        self._setup_logging()
        self._clear_logs()
        self._update_prompt()
        self._startup_output = f"radare2 session ready for {os.path.basename(self._program_path)}"

    def run_command(self, cmd: str, timeout: float | None = None) -> str:  # noqa: ARG002 - timeout kept for parity
        if self._r2 is None:
            raise RuntimeError("radare2 session is not initialized; call initialize_session()")

        text = (cmd or "").strip()
        if not text:
            return ""

        outputs: List[str] = []
        for part in self._split_commands(text):
            if not part:
                continue
            lower = part.lower()
            if lower in self._EXIT_COMMANDS:
                outputs.append(self._handle_exit(part))
                break
            self._clear_logs()
            err = ""
            try:
                out, err = self._execute(part)
            except Exception as exc:
                logs = self._drain_logs()
                self._update_prompt()
                combined = self._merge_output("", logs, err)
                if combined:
                    outputs.append(combined)
                else:
                    outputs.append(f"[radare2 error] {part}: {exc}")
                if isinstance(exc, RuntimeError) and "Process terminated unexpectedly" in str(exc):
                    self._r2 = None
                    try:
                        self.initialize_session()
                    except Exception as restart_exc:  # pragma: no cover - best effort recovery
                        outputs.append(f"[radare2 restart failed] {restart_exc}")
                        break
                continue
            logs = self._drain_logs()
            self._update_prompt()
            combined = self._merge_output(out, logs, err)
            if combined:
                outputs.append(combined)
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
            "e scr.color=true",
            "e scr.echo=false",
            "e scr.interactive=false",
            "e scr.clippy=false",
            "e bin.cache=true",
        ):
            try:
                self._r2.cmd(cmd)
            except Exception:
                pass

    def _execute(self, command: str) -> tuple[str, str]:
        if self._r2 is None:
            raise RuntimeError("radare2 session is not running")

        stdout_text, stderr_text = self._run_with_stderr_capture(lambda: self._r2.cmd(command))
        return self._sanitize_output(stdout_text), self._sanitize_output(stderr_text)

    def _run_with_stderr_capture(self, fn: Any) -> tuple[str, str]:
        read_fd, write_fd = os.pipe()
        saved_err = os.dup(2)
        try:
            os.dup2(write_fd, 2)
            os.close(write_fd)
            stdout_text = fn()
        finally:
            os.dup2(saved_err, 2)
            os.close(saved_err)
        stderr_text = ""
        try:
            with os.fdopen(read_fd, "r", encoding="utf-8", errors="ignore") as handle:
                stderr_text = handle.read()
        except Exception:
            try:
                os.close(read_fd)
            except Exception:
                pass
        return stdout_text, stderr_text

    def _sanitize_output(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("\r", "")
        lines = cleaned.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _setup_logging(self) -> None:
        if self._r2 is None:
            return
        if self._log_path is None:
            fd, path = tempfile.mkstemp(prefix="radare2-", suffix=".log")
            os.close(fd)
            self._log_path = path
        else:
            try:
                open(self._log_path, "w", encoding="utf-8").close()
            except Exception:
                fd, path = tempfile.mkstemp(prefix="radare2-", suffix=".log")
                os.close(fd)
                self._log_path = path
        self._log_offset = 0
        for cmd in (
            f"e log.file={self._log_path}",
            "e log.level=2",
            "e log.quiet=false",
        ):
            try:
                self._r2.cmd(cmd)
            except Exception:
                pass

    def _drain_logs(self) -> str:
        path = self._log_path
        if not path:
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(self._log_offset)
                data = handle.read()
                self._log_offset = handle.tell()
        except FileNotFoundError:
            return ""
        except Exception:
            return ""
        return data.strip()

    def _clear_logs(self) -> None:
        if self._log_path:
            self._drain_logs()

    def _merge_output(self, *chunks: str) -> str:
        parts: List[str] = []
        for chunk in chunks:
            if chunk:
                parts.append(chunk)
        return "\n".join(parts)

    def _update_prompt(self) -> None:
        if self._r2 is None:
            self.prompt = "radare2> "
            return
        try:
            addr = (self._r2.cmd("s") or "").strip()
        except Exception:
            self.prompt = "radare2> "
            return
        self.prompt = f"[{addr}]> " if addr else "radare2> "

    def _teardown_logging(self) -> None:
        path = self._log_path
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        finally:
            self._log_path = None
            self._log_offset = 0

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
            self._teardown_logging()

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
        finally:
            self._teardown_logging()
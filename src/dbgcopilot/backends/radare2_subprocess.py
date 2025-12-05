"""Radare2 backend implemented via r2pipe.

Uses the radare2 pipe API instead of driving an interactive TTY, which avoids
prompt-parsing issues and produces stable command output.
"""
from __future__ import annotations

from typing import Optional, List, Any
import os
import re
import subprocess
import tempfile
import threading
from collections import deque

try:
    import r2pipe  # type: ignore
except Exception:  # pragma: no cover - import error surfaced at runtime
    r2pipe = None  # type: ignore


_r2pipe_stderr_patched = False
_CSI_PRIVATE_MODE_RE = re.compile(r"\x1b\[\?[0-9;]*[hl]")



def _patch_r2pipe_for_stderr() -> None:
    """Ensure r2pipe launches radare2 with stderr piped so we can capture it."""

    global _r2pipe_stderr_patched
    if _r2pipe_stderr_patched or r2pipe is None:  # pragma: no cover - defensive
        return

    try:
        from r2pipe import open_sync as _open_sync  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        _r2pipe_stderr_patched = True
        return

    if getattr(_open_sync, "_copilot_stderr_patch", False):
        _r2pipe_stderr_patched = True
        return

    original_popen = _open_sync.Popen

    def _popen_with_stderr(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("stderr", subprocess.PIPE)
        return original_popen(*args, **kwargs)

    _open_sync.Popen = _popen_with_stderr  # type: ignore[assignment]
    _open_sync._copilot_stderr_patch = True  # type: ignore[attr-defined]
    _r2pipe_stderr_patched = True


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
        self._stderr_stream: Optional[Any] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_buffer: deque[str] = deque()
        self._stderr_lock = threading.Lock()

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

        _patch_r2pipe_for_stderr()

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

        self._attach_stderr_reader()
        self._configure_session()
        self._setup_logging()
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
            leading = self._collect_side_output()
            try:
                out = self._execute(part)
            except Exception as exc:
                trailing = self._collect_side_output()
                self._update_prompt()
                error_text = f"[radare2 error] {part}: {exc}"
                combined = self._merge_output(leading, trailing, error_text)
                outputs.append(combined if combined else error_text)
                if isinstance(exc, RuntimeError) and "Process terminated unexpectedly" in str(exc):
                    self._r2 = None
                    try:
                        self.initialize_session()
                    except Exception as restart_exc:  # pragma: no cover - best effort recovery
                        outputs.append(f"[radare2 restart failed] {restart_exc}")
                        break
                continue
            trailing = self._collect_side_output()
            self._update_prompt()
            combined = self._merge_output(leading, out, trailing)
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

    def _attach_stderr_reader(self) -> None:
        self._stderr_stream = None
        process = getattr(self._r2, "process", None)
        stream = getattr(process, "stderr", None)
        if not stream:
            return

        self._stderr_stream = stream
        self._stderr_buffer.clear()

        def _pump() -> None:
            try:
                while True:
                    chunk = stream.read(1024)
                    if not chunk:
                        break
                    if isinstance(chunk, bytes):
                        text = chunk.decode("utf-8", errors="ignore")
                    else:
                        text = chunk
                    cleaned = text.replace("\r", "")
                    if not cleaned.strip():
                        continue
                    with self._stderr_lock:
                        self._stderr_buffer.append(cleaned)
            except Exception:
                pass

        self._stderr_thread = threading.Thread(
            target=_pump,
            name="radare2-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    def _drain_stderr_buffer(self) -> str:
        if self._stderr_stream is None:
            return ""
        with self._stderr_lock:
            if not self._stderr_buffer:
                return ""
            data = "".join(self._stderr_buffer)
            self._stderr_buffer.clear()
        return self._sanitize_output(data)

    def _collect_side_output(self) -> str:
        parts: List[str] = []
        stderr_text = self._drain_stderr_buffer()
        if stderr_text:
            parts.append(stderr_text)
        logs = self._drain_logs()
        if logs:
            parts.append(logs)
        return self._merge_output(*parts)

    def _reset_stderr_capture(self) -> None:
        self._stderr_stream = None
        with self._stderr_lock:
            self._stderr_buffer.clear()

    def _execute(self, command: str) -> str:
        if self._r2 is None:
            raise RuntimeError("radare2 session is not running")

        output = self._r2.cmd(command)
        return self._sanitize_output(output)

    def _sanitize_output(self, text: str) -> str:
        if not text:
            return ""
        cleaned = _CSI_PRIVATE_MODE_RE.sub("", text)
        cleaned = cleaned.replace("\r", "")
        lines = cleaned.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _setup_logging(self) -> None:
        if self._r2 is None or self._stderr_stream is not None:
            # With stderr piped we already get WARN/INFO; logging file is redundant.
            self._log_path = None
            self._log_offset = 0
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
            "e log.cons=false",
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
            self._reset_stderr_capture()

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
            self._reset_stderr_capture()
"""Java debugging backend using the standard `jdb` tool.

Provides a subprocess-driven interface so the orchestrator can execute common
commands (`run`, `continue`, `print`, etc.) through `pexpect`, mirroring the
pattern used by other debugger backends.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, Tuple

try:  # pragma: no cover - optional dependency guard
    import pexpect  # type: ignore
except Exception:  # pragma: no cover - runtime dependency check
    pexpect = None  # type: ignore


class JavaJdbBackend:
    name = "jdb"
    prompt = "> "

    _ANSI_PATTERN = r"(?:\x1b\[[0-9;?]*[ -/]*[@-~])*"
    _PROMPT_PATTERN = re.compile(rf"{_ANSI_PATTERN}(?:[\w.$<>-]+\[\d+\]\s*)?>\s*")

    def __init__(
        self,
        program: Optional[str] = None,
        classpath: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.program = program
        self.classpath = classpath
        self.cwd = cwd
        self.timeout = timeout
        self.child: Optional[Any] = None
        self._prompt_re = self._PROMPT_PATTERN
        self._prepared: Optional[Tuple[list[str], Optional[str]]] = None
        self._startup_output: str = ""

    # ------------------------------------------------------------------
    # Session lifecycle
    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is required for the jdb backend")
        if shutil.which("jdb") is None:
            raise RuntimeError("jdb executable not found on PATH")
        if shutil.which("javac") is None:
            raise RuntimeError("javac executable not found on PATH")

    def close(self) -> None:
        if self.child is not None:
            try:
                if self.child.isalive():
                    self.child.terminate(force=True)
            except Exception:
                pass
        self.child = None
        self._prepared = None

    def _prefix(self) -> str:
        return f"[{self.name}]"

    # ------------------------------------------------------------------
    def run_command(self, command: str, timeout: float | None = None) -> str:
        cmd = (command or "").strip()
        if not cmd:
            return ""

        lower = cmd.lower()
        if lower.startswith("file "):
            target = cmd[5:].strip()
            if not target:
                return f"{self._prefix()} provide a path to a .java/.class/.jar or main class"
            resolved = self._resolve_program_path(target)
            self.program = resolved
            self._prepared = None
            self.close()
            return f"{self._prefix()} program set to {resolved}"

        if lower.startswith("classpath "):
            value = cmd[len("classpath ") :].strip()
            self.classpath = value or None
            self._prepared = None
            self.close()
            return f"{self._prefix()} classpath set to {value}" if value else f"{self._prefix()} classpath cleared"

        if lower in {"run", "r"}:
            return self._handle_run(timeout=timeout)

        if lower in {"quit", "exit", "q"}:
            if self.child and self.child.isalive():
                try:
                    self.child.sendline("quit")
                except Exception:
                    pass
            self.close()
            return f"{self._prefix()} session terminated"

        if lower in {"continue", "c"}:
            return self._send_and_capture("cont", timeout=timeout)
        if lower in {"next", "n"}:
            return self._send_and_capture("next", timeout=timeout)
        if lower in {"step", "s", "stepin"}:
            return self._send_and_capture("step", timeout=timeout)
        if lower in {"where", "bt", "backtrace"}:
            return self._send_and_capture("where", timeout=timeout)
        if lower in {"threads", "thread"}:
            return self._send_and_capture("threads", timeout=timeout)
        if lower.startswith("print ") or lower.startswith("p "):
            expr = cmd.split(" ", 1)[1].strip()
            if not expr:
                return f"{self._prefix()} provide an expression"
            return self._send_and_capture(f"print {expr}", timeout=timeout)
        if lower.startswith("locals"):
            return self._send_and_capture("locals", timeout=timeout)

        # Fallback: forward verbatim
        return self._send_and_capture(cmd, timeout=timeout)

    # ------------------------------------------------------------------
    def _handle_run(self, timeout: float | None = None) -> str:
        startup = self._ensure_session_started(timeout)
        if not self.child or not self.child.isalive():
            return startup or f"{self._prefix()} session ended"

        run_output = self._send_and_capture("run", timeout=timeout, ensure=False)
        pieces: list[str] = []
        if startup:
            pieces.append(startup)
        if run_output:
            pieces.append(run_output)
        return "\n".join(piece for piece in pieces if piece)

    def _prepare_launch(self) -> Tuple[list[str], Optional[str]]:
        if self._prepared:
            return self._prepared

        program = (self.program or "").strip()
        command: list[str]
        workdir: Optional[str] = None

        if not program:
            command = ["jdb"]
            self._prepared = (command, workdir)
            return command, workdir

        path = Path(program)

        if path.is_file():
            suffix = path.suffix.lower()
            if suffix == ".java":
                command, workdir = self._prepare_from_java(path)
            elif suffix == ".class":
                command, workdir = self._prepare_from_class(path)
            elif suffix == ".jar":
                command = ["jdb", "-jar", str(path.resolve())]
                workdir = path.parent.as_posix()
            else:
                raise ValueError(f"Unsupported file type: {path.suffix}")
        else:
            # treat as main class name, optionally using provided classpath
            main_class = program
            cp = self.classpath
            command = ["jdb"]
            if cp:
                command.extend(["-classpath", cp])
            if main_class:
                command.append(main_class)

        self._prepared = (command, workdir)
        return command, workdir

    def _prepare_from_java(self, source: Path) -> Tuple[list[str], Optional[str]]:
        src_path = source.resolve()
        if not src_path.exists():
            raise FileNotFoundError(src_path)
        package = self._detect_package(src_path)
        compile_dir = src_path.parent
        result = subprocess.run(
            ["javac", "-g", str(src_path)],
            cwd=compile_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        main_class = src_path.stem
        if package:
            main_class = f"{package}.{main_class}"
        cp = self.classpath or compile_dir.as_posix()
        cmd = ["jdb", "-classpath", cp, main_class]
        return cmd, compile_dir.as_posix()

    def _prepare_from_class(self, compiled: Path) -> Tuple[list[str], Optional[str]]:
        class_file = compiled.resolve()
        if not class_file.exists():
            raise FileNotFoundError(class_file)
        class_dir = class_file.parent
        main_class = class_file.stem
        cp = self.classpath or class_dir.as_posix()
        cmd = ["jdb", "-classpath", cp, main_class]
        return cmd, class_dir.as_posix()

    def _detect_package(self, source: Path) -> Optional[str]:
        try:
            with source.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("//"):
                        continue
                    if stripped.startswith("package ") and stripped.endswith(";"):
                        return stripped[len("package ") : -1].strip()
        except Exception:
            return None
        return None

    def _expect_prompt(self) -> str:
        assert self.child is not None
        assert pexpect is not None
        try:
            self.child.expect(self._prompt_re)
        except pexpect.TIMEOUT:
            return f"{self._prefix()} timeout waiting for jdb prompt"
        except pexpect.EOF:
            output = (self.child.before or "").strip()
            self.child = None
            return output or f"{self._prefix()} process exited"
        except Exception as exc:
            return f"{self._prefix()} failed waiting for jdb prompt: {exc}"
        return (self.child.before or "").strip()

    def _send_and_capture(self, command: str, timeout: float | None = None, *, ensure: bool = True) -> str:
        startup = ""
        if ensure:
            startup = self._ensure_session_started(timeout)
            if not self.child or not self.child.isalive():
                return startup or f"{self._prefix()} session ended"
        child = self.child
        if not child or not child.isalive():
            return startup or f"{self._prefix()} session ended"
        assert pexpect is not None
        try:
            child.sendline(command)
        except Exception as exc:
            return f"{self._prefix()} failed to send command: {exc}"
        try:
            child.expect(self._prompt_re, timeout=timeout or self.timeout)
            out = child.before or ""
            result = self._normalize_output(command, out)
            return self._combine_startup(startup, result)
        except pexpect.TIMEOUT:
            buffer = child.before or ""
            match = self._prompt_re.search(buffer)
            if match:
                captured = buffer[: match.start()]
                result = self._normalize_output(command, captured)
                return self._combine_startup(startup, result)
            partial = self._normalize_output(command, buffer)
            if partial:
                partial = f"{partial}\n{self._prefix()} timeout waiting for prompt after '{command}'"
                return self._combine_startup(startup, partial)
            return self._combine_startup(startup, f"{self._prefix()} timeout waiting for '{command}'")
        except pexpect.EOF:
            out = child.before or ""
            self.child = None
            normalized = self._normalize_output(command, out)
            merged = self._combine_startup(startup, normalized)
            return merged or f"{self._prefix()} process exited"

    def _normalize_output(self, command: str, captured: str) -> str:
        text = (captured or "").replace("\r\n", "\n").lstrip("\r\n")
        if text.startswith(command):
            text = text[len(command) :].lstrip()
        return text.strip()

    def _ensure_session_started(self, timeout: float | None = None) -> str:
        if self.child and self.child.isalive():
            return ""
        try:
            launch, workdir = self._prepare_launch()
        except Exception as exc:
            return f"{self._prefix()} failed to prepare program: {exc}"

        assert pexpect is not None
        try:
            self.child = pexpect.spawn(
                launch[0],
                launch[1:],
                encoding="utf-8",
                timeout=timeout or self.timeout,
                cwd=workdir or self.cwd,
            )
        except FileNotFoundError as exc:
            self.child = None
            return f"{self._prefix()} failed to start jdb: {exc}"
        except Exception as exc:
            self.child = None
            return f"{self._prefix()} failed to launch jdb: {exc}"

        startup = self._expect_prompt()
        if not self.child or not self.child.isalive():
            return startup or f"{self._prefix()} session ended"
        return startup

    def _combine_startup(self, startup: str, text: str) -> str:
        pieces = [piece for piece in (startup, text) if piece]
        return "\n".join(pieces)

    def _resolve_program_path(self, target: str) -> str:
        path = Path(target)
        if path.exists():
            return str(path.resolve())
        # allow plain class names without files
        return target

    # ------------------------------------------------------------------
    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass

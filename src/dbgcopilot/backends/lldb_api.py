"""LLDB API backend (standalone, no pexpect).

Creates and drives an LLDB SBDebugger instance via the Python API, mirroring the
in-process approach but usable from the standalone copilot> REPL.
"""
from __future__ import annotations

from typing import Optional, List
import sys
import os
import subprocess


class LldbApiBackend:
    name = "lldb"

    def __init__(self, use_color: bool = False) -> None:
        self._use_color = use_color
        self._lldb = None  # type: ignore
        self._dbg = None  # type: ignore
        self._interp = None  # type: ignore
        self._initialized_runtime = False

    def initialize_session(self) -> None:
        # Try importing lldb conservatively; if it fails the probe, we abort and let caller fall back.
        lldb = self._try_import_lldb()

        # Initialize the LLDB runtime once per-process
        if not self._initialized_runtime:
            lldb.SBDebugger.Initialize()
            self._initialized_runtime = True

        # Create a dedicated debugger instance for this backend
        self._lldb = lldb
        self._dbg = lldb.SBDebugger.Create()
        if not self._dbg:
            raise RuntimeError("Failed to create LLDB debugger")
        self._dbg.SetAsync(False)
        self._interp = self._dbg.GetCommandInterpreter()

        # Session-friendly defaults
        self._handle_command(f"settings set use-color {'true' if self._use_color else 'false'}")
        self._handle_command("settings set auto-confirm true")

    def _try_import_lldb(self):
        """Import lldb in a conservative, crash-avoidant way.

        Rules:
        - Do NOT preload liblldb via ctypes (can trigger fatal init paths).
        - Only manipulate sys.path using LLDB_PYTHON_DIR/LLDB_PYTHONPATH or `lldb -P`.
        - First probe import in a short subprocess; only import in-process if probe succeeds.
        """
        # Allow users to disable API path explicitly
        if os.environ.get("DBGCOPILOT_LLDB_API", "1").lower() in {"0", "false", "no"}:
            raise RuntimeError("LLDB Python API disabled by DBGCOPILOT_LLDB_API=0")

        # Candidate paths from env and lldb -P
        py_paths: list[str] = []
        for env_key in ("LLDB_PYTHON_DIR", "LLDB_PYTHONPATH"):
            p = os.environ.get(env_key)
            if p and os.path.isdir(p):
                py_paths.append(p)
        try:
            out = subprocess.check_output(["lldb", "-P"], text=True, stderr=subprocess.DEVNULL).strip()
            if out and os.path.isdir(out):
                py_paths.append(out)
        except Exception:
            pass

        # Dedup while preserving order
        seen = set()
        py_paths = [x for x in py_paths if not (x in seen or seen.add(x))]

        def _probe() -> bool:
            code = (
                "import sys, os; paths=%r;\n"
                "[sys.path.insert(0,p) for p in paths if p not in sys.path];\n"
                "import lldb; import sys;\n"
                "print('OK', getattr(lldb,'__file__','n/a'));\n"
            ) % (py_paths or [])
            try:
                proc = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                return proc.returncode == 0
            except Exception:
                return False

        # Probe first; if it fails, do not import in-process
        if not _probe():
            hint = (
                "LLDB Python module could not be imported safely in a probe. Options:\n"
                "- Linux: sudo apt install lldb python3-lldb liblldb-18; then set PYTHONPATH=$(lldb -P)\n"
                "- macOS: install Xcode CLT; run with PYTHONPATH=$(lldb -P) python3 -c 'import lldb'\n"
                "- Conda: conda install -c conda-forge lldb\n"
                "Or set DBGCOPILOT_LLDB_API=0 to force subprocess backend."
            )
            raise RuntimeError(hint)

        # Import in-process using only path injection, mirroring the probe
        for p in py_paths:
            if p not in sys.path:
                sys.path.insert(0, p)
        import lldb  # type: ignore
        return lldb

    def _handle_command(self, command: str) -> str:
        """Run a single LLDB command via the interpreter and return output or error."""
        if not self._interp:
            raise RuntimeError("LLDB API backend not initialized")
        res = self._lldb.SBCommandReturnObject()  # type: ignore[attr-defined]
        self._interp.HandleCommand(command, res)
        if res.Succeeded():
            return (res.GetOutput() or "").rstrip("\n")
        else:
            err = res.GetError() or ""
            return (err or "").rstrip("\n")

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        # Split into individual commands (newline/semicolon separated)
        parts: List[str] = []
        for chunk in (cmd or "").replace("\r", "\n").split("\n"):
            parts.extend([p.strip() for p in chunk.split(";") if p.strip()])
        if not parts:
            parts = [cmd.strip()]

        outputs: List[str] = []
        for part in parts:
            # SBCommandInterpreter is synchronous; timeout is not supported here
            try:
                out = self._handle_command(part)
            except Exception as e:
                out = f"[lldb api error] {part}: {e}"
            if out:
                outputs.append(out)
        return "\n".join(outputs)

    def __del__(self):  # pragma: no cover
        try:
            if self._dbg is not None and self._lldb is not None:
                self._lldb.SBDebugger.Destroy(self._dbg)
        except Exception:
            pass

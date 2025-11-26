"""Rust-focused LLDB backend.

Extends the subprocess LLDB driver with Rust-friendly defaults so the assistant
can offer a smoother experience when debugging Cargo-built binaries.
"""
from __future__ import annotations

import shutil
from typing import Iterable

from .lldb_subprocess import LldbSubprocessBackend


class LldbRustBackend(LldbSubprocessBackend):
    name = "rust-lldb"

    def __init__(self, lldb_path: str | None = None, timeout: float = 10.0) -> None:
        if lldb_path is None:
            rust_lldb = shutil.which("rust-lldb")
            lldb_path = rust_lldb or "lldb"
        super().__init__(lldb_path=lldb_path, timeout=timeout, prompt="(rust-lldb)")

    def initialize_session(self) -> None:
        super().initialize_session()
        self._apply_rust_defaults()

    def _apply_rust_defaults(self) -> None:
        commands: Iterable[str] = (
            "settings set target.process.thread.step-avoid-regexp '^(__rust_begin_short_backtrace|core::|std::)'",
            "command alias bt backtrace",
        )
        for cmd in commands:
            try:
                self.run_command(cmd)
            except Exception:
                continue
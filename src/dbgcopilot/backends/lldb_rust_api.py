"""Rust-flavoured LLDB backend built on the Python API.

Prefers the in-process LLDB API path (like :mod:`lldb_api`) but applies the same
Rust-oriented defaults that the subprocess backend configures. Falling back to
this backend avoids the flaky output capture sometimes seen with the
`rust-lldb` subprocess.
"""
from __future__ import annotations

from typing import Iterable

from .lldb_api import LldbApiBackend


class LldbRustApiBackend(LldbApiBackend):
    name = "lldb-rust"

    def __init__(self, use_color: bool = True) -> None:
        super().__init__(use_color=use_color)
        # Expose a prompt consistent with the subprocess backend so the REPL
        # can strip it when formatting output.
        self.prompt = "(lldb-rust) "

    def initialize_session(self) -> None:
        super().initialize_session()
        self._apply_rust_defaults()

    def _apply_rust_defaults(self) -> None:
        commands: Iterable[str] = (
            "settings set target.process.thread.step-avoid-regexp '^(__rust_begin_short_backtrace|core::|std::)'",
            "settings set prompt (lldb-rust) ",
            "command alias bt backtrace",
        )
        for cmd in commands:
            try:
                self.run_command(cmd)
            except Exception:
                # Best-effort configuration; ignore issues so the backend stays usable.
                continue

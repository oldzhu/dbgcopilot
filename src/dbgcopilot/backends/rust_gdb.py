"""Rust-aware GDB subprocess backend."""
from __future__ import annotations

import shutil

from .gdb_subprocess import GdbSubprocessBackend


class RustGdbBackend(GdbSubprocessBackend):
    name = "rust-gdb"

    def __init__(self, gdb_path: str | None = None, timeout: float = 10.0) -> None:
        if gdb_path is None:
            rust_gdb = shutil.which("rust-gdb")
            gdb_path = rust_gdb or "gdb"
        super().__init__(gdb_path=gdb_path, timeout=timeout)

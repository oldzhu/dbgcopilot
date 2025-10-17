"""Debugger backend interface (POC)."""
from __future__ import annotations

from typing import Protocol


class DebuggerBackend(Protocol):
    def run_command(self, cmd: str, timeout: float | None = None) -> str:  # pragma: no cover
        ...

    def initialize_session(self) -> None:  # pragma: no cover
        ...

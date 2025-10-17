"""GDB in-process backend (POC placeholder).

In future iterations, this will call into gdb.execute / gdb.selected_frame, etc.
For now, it returns canned output for demonstration.
"""
from __future__ import annotations

class GdbInProcessBackend:
    def initialize_session(self) -> None:
        # TODO: set pagination off, height 0, width large, etc.
        pass

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        # TODO: use gdb Python API to execute and capture text
        if cmd.strip() == "bt":
            return "#0  0x00000000 in ?? ()\n#1  main () at demo.c:12"
        return f"(placeholder output) ran: {cmd}"

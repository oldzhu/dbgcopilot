"""Helpers for validating debugger tooling availability."""
from __future__ import annotations

import shutil
import sys
from typing import Iterable

DEBUGGER_INSTALL_DOC = "https://github.com/oldzhu/dbgcopilot/blob/main/docs/install.md#prerequisites"

DEBUGGER_EXECUTABLES: dict[str, str] = {
    "gdb": "GDB",
    "lldb": "LLDB",
    "dlv": "Delve (dlv)",
    "radare2": "Radare2",
    "jdb": "jdb",
}


def missing_debugger_tools() -> list[str]:
    """Return the debugger executables that are not on PATH."""
    return [name for name in DEBUGGER_EXECUTABLES if shutil.which(name) is None]


def warn_missing_debugger_tools(context: str = "dbg") -> None:
    """Print a reminder if any debugger binary is missing."""
    missing = missing_debugger_tools()
    if not missing:
        return
    names = ", ".join(sorted(missing))
    print(
        (
            f"[{context}] Missing debugger tools: {names}."
            f" See {DEBUGGER_INSTALL_DOC} for install instructions."
        ),
        file=sys.stderr,
    )

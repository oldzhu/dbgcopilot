"""I/O helpers (POC).

ANSI color helpers for optional colored output in REPL and summaries.
"""
from __future__ import annotations

import re


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def head_tail_truncate(s: str, max_chars: int = 20000) -> str:
    if len(s) <= max_chars:
        return s
    head = s[: max_chars // 2]
    tail = s[-max_chars // 2 :]
    return head + "\n... [truncated] ...\n" + tail

# Basic ANSI color codes
_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "faint": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}


def color_text(s: str, color: str | None = None, bold: bool = False, enable: bool = True) -> str:
    """Wrap text with ANSI color codes if enabled.

    - color: one of keys in _CODES (e.g., 'green', 'cyan') or None for no color
    - bold: add bold attribute
    - enable: if False, returns s unchanged
    """
    if not enable or not color or color not in _CODES:
        return s
    prefix = (_CODES["bold"] if bold else "") + _CODES[color]
    return f"{prefix}{s}{_CODES['reset']}"


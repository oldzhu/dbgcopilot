"""I/O helpers (POC)."""
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

"""LLDB in-process backend.

Uses LLDB's Python API (lldb module) to run commands when inside LLDB; falls back
to placeholders when the lldb Python module isn't available (e.g., unit tests).
"""
from __future__ import annotations


class LldbInProcessBackend:
    name = "lldb"

    def __init__(self) -> None:
        self.prompt = "(lldb) "

    def initialize_session(self) -> None:
        # Minimal session tweaks can be added here if needed (e.g., settings set ...)
        try:
            import lldb  # type: ignore  # noqa: F401
        except Exception:
            pass

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        """Execute one LLDB command and return its textual output.

        Notes:
        - LLDB's API processes one command per call; if multiple are provided, we split on newlines/';'.
        - If not inside LLDB (no lldb module), return placeholder output.
        """
        try:
            import lldb  # type: ignore
            dbg = lldb.debugger
            interp = dbg.GetCommandInterpreter()
        except Exception:
            # Placeholder outside of LLDB
            if cmd.strip() in {"bt", "thread backtrace"}:
                return "* thread #1, stop reason = signal SIGSEGV\n  * frame #0: 0x00000000"
            return f"(placeholder output) ran: {cmd}"

        outputs: list[str] = []
        parts: list[str] = []
        for chunk in cmd.replace("\r", "\n").split("\n"):
            parts.extend([p.strip() for p in chunk.split(";") if p.strip()])

        for part in parts or [cmd.strip()]:
            res = lldb.SBCommandReturnObject()
            interp.HandleCommand(part, res)
            text = ""
            if res.Succeeded():
                text = res.GetOutput() or ""
            else:
                err = res.GetError() or ""
                text = (text + err) if err else text
            outputs.append(text)

        return "\n".join(o for o in outputs if o)

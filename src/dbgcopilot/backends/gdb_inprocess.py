"""GDB in-process backend.

Uses gdb.execute to run commands when inside GDB; falls back to placeholders
when the gdb Python module isn't available (e.g., unit tests).
"""
from __future__ import annotations

class GdbInProcessBackend:
    name = "gdb"

    def initialize_session(self) -> None:
        # Configure GDB output to be script-friendly
        try:  # Import only works inside GDB
            import gdb  # type: ignore

            gdb.execute("set pagination off", to_string=True)
            gdb.execute("set height 0", to_string=True)
            gdb.execute("set width 0", to_string=True)
            # Avoid interactive debuginfod prompt loops in non-interactive REPL usage
            try:
                gdb.execute("set debuginfod enabled off", to_string=True)
            except Exception:
                pass
        except Exception:
            # Not running inside GDB or settings failed; ignore
            pass

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        """Execute one or more GDB commands and return concatenated output.

        - Supports multiple commands separated by ';' or newlines. Executes in order.
        - Catches gdb.error per command and appends the error text instead of throwing.
        - Enhances output for state-changing commands by appending stop reason and a short bt.
        - Falls back to placeholder only when not inside GDB (no gdb module).
        """
        # Detect if we're inside GDB
        try:
            import gdb  # type: ignore
        except Exception:
            if cmd.strip() == "bt":
                return "#0  0x00000000 in ?? ()\n#1  main () at demo.c:12"
            return f"(placeholder output) ran: {cmd}"

        outputs: list[str] = []
        # Split on ';' and newlines for simple multi-command sequences
        parts = []
        for chunk in cmd.replace("\r", "\n").split("\n"):
            parts.extend([p.strip() for p in chunk.split(";") if p.strip()])

        for part in parts or [cmd.strip()]:
            try:
                # Run as-if typed by a human (from_tty=True) but capture output (to_string=True)
                out = gdb.execute(part, from_tty=True, to_string=True)
                text = out if isinstance(out, str) else str(out)
            except Exception as e:  # gdb.error or others
                text = f"[gdb error] {e}"

            lower = part.lower()
            if lower.startswith(("run", "r", "continue", "c", "next", "n", "step", "s", "finish", "start")):
                # Append stop reason and short backtrace
                try:
                    stop = gdb.execute("info program", to_string=True)
                except Exception:
                    stop = ""
                try:
                    bt = gdb.execute("bt 5", to_string=True)
                except Exception:
                    bt = ""
                if stop:
                    if text and not text.endswith("\n"):
                        text += "\n"
                    text += stop
                if bt:
                    if text and not text.endswith("\n"):
                        text += "\n"
                    text += bt
            # For 'file' and similar loader commands, GDB usually prints 'Reading symbols...' when from_tty
            # We've already run with from_tty=True above so such messages should be included in 'text'.
            outputs.append(text)

        return "\n".join(o for o in outputs if o)

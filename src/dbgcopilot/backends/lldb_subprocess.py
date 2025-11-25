"""LLDB subprocess backend using pexpect.

Spawns an interactive `lldb` process and drives it via a pseudo-tty.
Used by the standalone copilot> REPL outside of LLDB.
"""
from __future__ import annotations

from typing import Optional, List
import re

try:
    import pexpect
except Exception:
    pexpect = None  # type: ignore


_DWARF_INDEXING_RE = re.compile(r"^\s*\[\d+/\d+\]\s+Manually indexing DWARF:.*$")


class LldbSubprocessBackend:
    name = "lldb"

    def __init__(self, lldb_path: str = "lldb", timeout: float = 10.0, prompt: str = "(lldb)") -> None:
        self.lldb_path = lldb_path
        self.timeout = timeout
        self.prompt = prompt
        self.child: Optional[pexpect.spawn] = None  # type: ignore
        self._default_prompt_re = re.compile(r"\(lldb\)\s", re.MULTILINE)
        self._prompt_re: Optional[re.Pattern[str]] = None
        # Tracking for reliability hints
        self._empty_count: int = 0
        self._empty_threshold: int = 2
        self._suggested_once: bool = False
        self._ansi_seqs = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
        self._timeout_reported: bool = False

    def initialize_session(self) -> None:
        if pexpect is None:
            raise RuntimeError("pexpect is not available; cannot start subprocess backend")
        # Launch LLDB. Use encoding for string I/O.
        self.child = pexpect.spawn(self.lldb_path, [], encoding="utf-8", timeout=self.timeout)
        # Immediately set a simple prompt we can match reliably, then expect it
        ansi = r"(?:\x1b\[[0-9;]*m)*"
        try:
            # Flush the default prompt before switching to our own
            self._expect_prompt()
        except Exception:
            pass
        try:
            # Send the custom prompt before expecting it with the new regex
            self.child.sendline(f"settings set prompt {self.prompt} ")
            self._prompt_re = re.compile(ansi + re.escape(self.prompt) + ansi + r"\s*")
            self._expect_prompt()
        except Exception:
            # Nudge with a newline and try again in case the prompt change emitted extra noise
            try:
                self.child.sendline("")
                if self._prompt_re:
                    self._expect_prompt()
                else:
                    self.child.expect(self._default_prompt_re)
            except Exception:
                pass
        # Configure non-interactive friendly behavior (after prompt is set)
        try:
            self._send_and_capture("settings set auto-confirm true")
        except Exception:
            pass
        # Configuration that changes color/behavior will respect `/colors` later.
        self._timeout_reported = False


    def _expect_prompt(self) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not running")
        # Expect the custom prompt if available, else fallback to default
        pat = self._prompt_re or self._default_prompt_re
        self.child.expect(pat)
        return self.child.before or ""

    def _strip_ansi(self, chunk: str) -> str:
        return self._ansi_seqs.sub("", chunk)

    def _filter_dwarf_noise(self, text: str) -> str:
        if not text:
            return text
        noisy_prefixes = (
            "Locating external symbol file:",
            "Parsing symbol table:",
            "Reading binary from memory:",
        )
        lines = text.splitlines()
        filtered: List[str] = []
        for ln in lines:
            stripped = self._strip_ansi(ln).strip()
            if not stripped:
                continue
            if _DWARF_INDEXING_RE.match(stripped):
                continue
            if any(stripped.startswith(pref) for pref in noisy_prefixes):
                continue
            filtered.append(ln)
        return "\n".join(filtered)

    def _send_and_capture_raw(self, cmd: str, timeout: Optional[float] = None) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not running")
        self.child.sendline(cmd)
        old_timeout = self.child.timeout
        if timeout is not None:
            self.child.timeout = timeout
        try:
            out = ""
            sanitized = cmd.replace("\r", "").split("\n", 1)[0].strip()
            max_cycles = 8
            last_chunk = ""
            for _ in range(max_cycles):
                chunk = self._expect_prompt()
                last_chunk = chunk
                if not chunk:
                    continue
                stripped = self._strip_ansi(chunk)
                if not stripped.strip():
                    continue
                out = chunk
                if sanitized and stripped.lstrip().startswith(sanitized):
                    break
                if not sanitized:
                    break
        finally:
            self.child.timeout = old_timeout
        return out or last_chunk

    def _send_and_capture(self, cmd: str, timeout: Optional[float] = None) -> str:
        # Wrap raw capture and remove any echoed command line
        try:
            out = self._send_and_capture_raw(cmd, timeout=timeout)
        except pexpect.TIMEOUT:  # type: ignore[attr-defined]
            if self._timeout_reported:
                return ""
            self._timeout_reported = True
            return f"[lldb timeout] {cmd}: Timeout exceeded."
        except pexpect.EOF:  # type: ignore[attr-defined]
            self._shutdown_child()
            return ""
        raw = out or ""
        filtered = self._filter_dwarf_noise(raw)
        text = filtered.lstrip("\r\n")
        lines = text.splitlines()
        if lines:
            first_clean = self._strip_ansi(lines[0]).strip()
            if first_clean == cmd.strip():
                lines = lines[1:]
        return "\n".join(lines)

    def _shutdown_child(self) -> None:
            try:
                if self.child and self.child.isalive():
                    self.child.close(force=True)
            except Exception:
                pass
            finally:
                self.child = None

    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        if not self.child:
            raise RuntimeError("LLDB subprocess is not initialized; call initialize_session()")
        # Avoid splitting Python after 'script ' — keep as a single command
        raw = (cmd or "").strip()
        if raw.lower().startswith("script "):
            parts = [raw]
        else:
            parts: List[str] = []
            for chunk in raw.replace("\r", "\n").split("\n"):
                parts.extend([p.strip() for p in chunk.split(";") if p.strip()])
            if not parts:
                parts = [raw]

        outputs: List[str] = []
        for part in parts:
            try:
                out = self._send_and_capture(part, timeout=timeout)
            except pexpect.TIMEOUT:  # type: ignore[attr-defined]
                # Count timeouts as empty to trigger suggestions
                self._empty_count += 1
                outputs.append(f"[lldb timeout] {part}: Timeout exceeded.")
                continue
            except pexpect.EOF as e:  # type: ignore[attr-defined]
                outputs.append(f"[lldb eof] {part}: {e}")
                break
            except Exception as e:
                outputs.append(f"[lldb error] {part}: {e}")
                continue
            norm = (out or "").replace("\r\n", "\n")
            if norm.startswith("[lldb timeout]"):
                self._empty_count += 1
                outputs.append(norm)
                continue
            if norm.strip():
                self._empty_count = 0
            else:
                self._empty_count += 1
            outputs.append(norm)

        rendered = "\n".join(o for o in outputs if o)
        # Reliability hint when we see consecutive empty or timeout outputs
        if not self._suggested_once and self._empty_count >= self._empty_threshold:
            self._suggested_once = True
            hint = self._install_hint()
            suggest_lines = [
                "[copilot] Observed consecutive empty/timeout outputs from LLDB subprocess.",
                "For more reliable capture, try the LLDB Python API backend (preferred).",
                hint,
                "If you're inside LLDB, prefer the in-process plugin:",
                "  (lldb) command script import dbgcopilot.plugins.lldb.copilot_cmd; copilot",
            ]
            suggest_text = "\n".join(suggest_lines)
            return (rendered + ("\n" if rendered else "")) + suggest_text
        return rendered

    @staticmethod
    def _install_hint() -> str:
        try:
            import sys as _sys
            plat = _sys.platform
        except Exception:
            plat = ""
        if plat.startswith("linux"):
            return "Hint: install LLDB Python bindings: sudo apt install lldb python3-lldb"
        if plat == "darwin":
            return "Hint: install Xcode CLT, then verify: xcrun python3 -c 'import lldb' (or conda install -c conda-forge lldb)"
        if plat.startswith("win"):
            return "Hint: use Conda to install LLDB Python: conda install -c conda-forge lldb"
        return "Hint: install LLDB Python bindings (e.g., conda install -c conda-forge lldb)"

    def __del__(self):  # pragma: no cover
        try:
            if self.child and self.child.isalive():
                try:
                    self.child.sendline("quit")
                    self.child.expect(pexpect.EOF, timeout=1)  # type: ignore[arg-type]
                except Exception:
                    self.child.close(force=True)
        except Exception:
            pass

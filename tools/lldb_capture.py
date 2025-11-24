import re
import sys
import time

import pexpect

PROMPT = "(lldb)"
ANSI_SEQS = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PROMPT_RE = re.compile(r"(?:\x1b\[[0-9;]*m)*" + re.escape(PROMPT) + r"(?:\x1b\[[0-9;]*m)*\s*")

LOG = True


def _expect_prompt(child: pexpect.spawn, timeout: float = 15.0) -> str:
    child.expect(PROMPT_RE, timeout=timeout)
    return child.before or ""


def _has_text(chunk: str) -> bool:
    return bool(ANSI_SEQS.sub("", chunk).strip())


def send_command(child: pexpect.spawn, command: str, iterations: int = 6) -> str:
    if LOG:
        print(f"== sending [{command}] ==")
    child.sendline(command)
    captured = ""
    for i in range(iterations):
        chunk = _expect_prompt(child)
        if LOG:
            print(f"cycle {i}: repr={repr(chunk)}")
        if _has_text(chunk):
            captured = chunk
            break
    return normalize_output(captured)


def normalize_output(raw: str) -> str:
    return raw.replace("\r\n", "\n").strip()


def main() -> None:
    child = pexpect.spawn("lldb", [], encoding="utf-8", timeout=15)
    child.sendline("settings set use-color false")
    child.sendline(f"settings set prompt {PROMPT} ")
    time.sleep(0.1)
    _expect_prompt(child)
    commands = ["help", "help br", "help break"]
    for cmd in commands:
        out = send_command(child, cmd)
        print("OUTPUT:", repr(out))
        print("---")
    child.sendline("quit")
    child.expect(pexpect.EOF)


if __name__ == "__main__":
    main()

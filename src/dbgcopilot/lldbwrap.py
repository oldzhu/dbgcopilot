"""Launch LLDB with dbgcopilot available on sys.path and optionally preloaded.

This wrapper mirrors dbgcopilot-gdb but for LLDB. It exports PYTHONPATH to include
the installed location of the `dbgcopilot` package and can preload the copilot
command so `copilot` is immediately available.

Usage:
  dbgcopilot-lldb [--no-preload] [--] <lldb-args...>

Examples:
  dbgcopilot-lldb -Q -o "script import dbgcopilot; print('OK')" -o quit
  dbgcopilot-lldb -- /path/to/binary -c /path/to/core
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _compute_site_packages_for_package(pkg_name: str) -> Path:
    mod = __import__(pkg_name)
    return Path(mod.__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-preload", action="store_true", help="Do not preload the copilot plugin")
    parser.add_argument("--help", action="store_true", help="Show help and exit")
    if "--" in argv:
        idx = argv.index("--")
        ours, lldb_args = argv[:idx], argv[idx + 1 :]
    else:
        ours, lldb_args = [a for a in argv if a.startswith("-")], [a for a in argv if not a.startswith("-")]
    ns, _ = parser.parse_known_args(ours)
    if ns.help:
        print(__doc__.strip())
        return 0

    try:
        site_pkgs = _compute_site_packages_for_package("dbgcopilot")
    except Exception as e:
        print(f"[dbgcopilot-lldb] Failed to locate installed package: {e}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    new_pp = str(site_pkgs) if not existing else str(site_pkgs) + os.pathsep + existing
    env["PYTHONPATH"] = new_pp
    env.setdefault("PYTHONIOENCODING", "utf-8")

    preload = []
    if not ns.no_preload:
        # LLDB: execute a command on startup via -o / --one-line
        preload = ["-o", "command script import dbgcopilot.plugins.lldb.copilot_cmd"]

    cmd = ["lldb", *preload, *lldb_args]
    try:
        return subprocess.call(cmd, env=env)
    except FileNotFoundError:
        print("[dbgcopilot-lldb] 'lldb' not found on PATH", file=sys.stderr)
        return 127


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

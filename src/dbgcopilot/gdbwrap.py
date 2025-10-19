"""Launch GDB with dbgcopilot available on sys.path and optionally preloaded.

This wrapper avoids modifying system site-packages by exporting PYTHONPATH to
include the installed location of the `dbgcopilot` package. It can also preload
the Copilot GDB command so `copilot` is immediately available.

Usage:
  dbgcopilot-gdb [--no-preload] [--] <gdb-args...>

Examples:
  dbgcopilot-gdb -q -ex "python import dbgcopilot; print('OK')" -ex quit
  dbgcopilot-gdb -- /path/to/binary core
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _compute_site_packages_for_package(pkg_name: str) -> Path:
    mod = __import__(pkg_name)
    # .../site-packages/dbgcopilot/__init__.py -> site-packages
    return Path(mod.__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-preload", action="store_true", help="Do not preload the copilot plugin")
    parser.add_argument("--help", action="store_true", help="Show help and exit")
    # Split on explicit '--' to separate our args from gdb's args
    if "--" in argv:
        idx = argv.index("--")
        ours, gdb_args = argv[:idx], argv[idx + 1 :]
    else:
        ours, gdb_args = [a for a in argv if a.startswith("-")], [a for a in argv if not a.startswith("-")]
    ns, _ = parser.parse_known_args(ours)
    if ns.help:
        print(__doc__.strip())
        return 0

    # Find the site-packages containing dbgcopilot
    try:
        site_pkgs = _compute_site_packages_for_package("dbgcopilot")
    except Exception as e:
        print(f"[dbgcopilot-gdb] Failed to locate installed package: {e}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    new_pp = str(site_pkgs) if not existing else str(site_pkgs) + os.pathsep + existing
    env["PYTHONPATH"] = new_pp
    # Ensure UTF-8 for Python I/O inside GDB's embedded interpreter
    env.setdefault("PYTHONIOENCODING", "utf-8")

    # Preload the copilot plugin (so the `copilot` command exists)
    preload = []
    if not ns.no_preload:
        preload = ["-ex", "python import dbgcopilot.plugins.gdb.copilot_cmd"]

    # Exec gdb with passthrough args
    cmd = ["gdb", *preload, *gdb_args]
    try:
        return subprocess.call(cmd, env=env)
    except FileNotFoundError:
        print("[dbgcopilot-gdb] 'gdb' not found on PATH", file=sys.stderr)
        return 127


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

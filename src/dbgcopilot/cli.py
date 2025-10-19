"""Small CLI helpers for installed package.

Provides a `dbgcopilot-plugin-path` console script that prints the absolute
path to the GDB plugin file so users can source it easily from GDB.
"""
from __future__ import annotations

import os


def get_plugin_path() -> str:
    import dbgcopilot

    pkg_dir = os.path.dirname(dbgcopilot.__file__)
    return os.path.join(pkg_dir, "plugins", "gdb", "copilot_cmd.py")


def print_plugin_path() -> None:
    print(get_plugin_path())


if __name__ == "__main__":
    print_plugin_path()

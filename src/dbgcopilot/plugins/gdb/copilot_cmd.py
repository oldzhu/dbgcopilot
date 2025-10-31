"""GDB 'copilot' command scaffolding (packaged).

Usage inside gdb:
  (gdb) python import dbgcopilot.plugins.gdb.copilot_cmd  # registers command
  (gdb) copilot
  (gdb) copilot new

You can also `source` this file by its absolute path from the installed package.
"""

import sys
import uuid

# Try to import gdb module (only available inside GDB)
try:  # pragma: no cover - only available inside gdb
    import gdb  # type: ignore
except Exception:  # pragma: no cover
    gdb = None  # type: ignore

# If this file is 'sourced' directly by GDB, ensure later imports of
# 'dbgcopilot.plugins.gdb.copilot_cmd' refer to this same module object.
if __name__ != "dbgcopilot.plugins.gdb.copilot_cmd":  # pragma: no cover
    sys.modules["dbgcopilot.plugins.gdb.copilot_cmd"] = sys.modules.get(__name__)  # type: ignore[index]


def _ensure_paths():  # pragma: no cover - depends on runtime
    """When this file is 'sourced' directly, ensure site-packages is on sys.path."""
    import os
    # Add site-packages (parent of the package dir) so imports like
    # `import dbgcopilot` work when this file is sourced directly.
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../site-packages/dbgcopilot
    site_pkgs = os.path.dirname(pkg_root)  # .../site-packages
    if site_pkgs and site_pkgs not in sys.path:
        sys.path.insert(0, site_pkgs)
    # Dev convenience: if running from a repo layout, also try adding repo/src
    repo_src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(pkg_root)))), "src")
    if os.path.isdir(repo_src) and repo_src not in sys.path:
        sys.path.insert(0, repo_src)


_ensure_paths()

from dbgcopilot.core.state import SessionState, Attempt
from dbgcopilot.core.orchestrator import CopilotOrchestrator
from dbgcopilot.backends.gdb_inprocess import GdbInProcessBackend


# Globals kept in this module for REPL/state access
SESSION = None  # type: ignore
ORCH = None  # type: ignore
BACKEND = GdbInProcessBackend()


def _ensure_session():  # pragma: no cover - gdb environment
    """Ensure a session exists. Create one lazily if missing."""
    global SESSION, ORCH
    if SESSION is None:
        sid = str(uuid.uuid4())[:8]
        SESSION = SessionState(session_id=sid)
        ORCH = CopilotOrchestrator(BACKEND, SESSION)
        BACKEND.initialize_session()
        if gdb is not None:
            gdb.write(f"[copilot] New session: {sid}\n")
    else:
        ORCH = CopilotOrchestrator(BACKEND, SESSION)


if gdb is not None:  # pragma: no cover - only define the command inside gdb
    class CopilotCmd(gdb.Command):  # type: ignore
        """Single `copilot` command to launch the copilot> prompt."""

        def __init__(self) -> None:
            super().__init__("copilot", gdb.COMMAND_USER)

        def invoke(self, arg, from_tty):  # pragma: no cover - gdb environment
            global SESSION, ORCH
            args = (arg or "").strip()
            if args == "new":
                # force new session
                sid = str(uuid.uuid4())[:8]
                SESSION = SessionState(session_id=sid)
                ORCH = CopilotOrchestrator(BACKEND, SESSION)
                BACKEND.initialize_session()
                gdb.write(f"[copilot] New session: {sid}\n")
            else:
                # ensure a session exists
                _ensure_session()

            # Start nested prompt directly
            try:
                from dbgcopilot.plugins.gdb.repl import start_repl
                start_repl()
            except Exception:
                # Fallback to executing via gdb if direct import fails
                gdb.execute("python from dbgcopilot.plugins.gdb.repl import start_repl; start_repl()")

    def register():  # pragma: no cover
        CopilotCmd()

    register()

# Debugger Copilot — Session Notes

Purpose: Keep a lightweight record of key decisions and quick steps so context survives container restarts.

Decisions
- UX: Nested copilot> REPL inside GDB + optional hybrid view (Markdown/HTML report) for side viewing.
- Licensing: Apache-2.0 WITH LLVM-exception (aligns with LLDB/LLVM).
- Container-first workflow: Use Docker dev image (no local venv needed).

Quick steps
- Build dev image: `make docker-build`
- Run tests: `make docker-pytest`
- Shell in container: `make docker-shell`
- GDB/LLDB in container: `make gdb-shell` / `make lldb-shell`
- GDB plugin (inside gdb): `source /workspace/plugins/gdb/copilot_cmd.py`, then `copilot new`

Next work items
- Implement real GDB in-process backend (gdb.execute to_string=True, disable pagination).
- Wire LangChain prompts for ask/suggest/plan/auto.
- Add "view" command to auto-update reports/<session>.md.

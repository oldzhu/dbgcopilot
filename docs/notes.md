# Notes & Platform Tips

- GDB runs an embedded Python that does not automatically use your venv. The launcher and the `~/.gdbinit` snippet make `import dbgcopilot` work consistently inside GDB.
- For quick tests, you can also rely on `python import dbgcopilot.plugins.gdb.copilot_cmd` inside GDB to register the `copilot` command directly.
- The assistant now uses an LLM-driven flow. If it decides to run a command, it responds with `<cmd>…</cmd>` and the orchestrator executes it immediately; otherwise, it answers normally.

## LLDB Python API (optional)

For the best LLDB experience, the standalone REPL uses the LLDB Python API to execute commands and capture output. If the `lldb` Python module is not present, we automatically fall back to a subprocess backend.

Install the `lldb` module via your platform package manager:

- Ubuntu/Debian:
  ```bash
  sudo apt update
  sudo apt install lldb python3-lldb  # or: sudo apt install python3-lldb-<version>
  ```
- macOS (Xcode/Command Line Tools):
  ```bash
  xcode-select --install   # if needed
  xcrun python3 -c 'import lldb; print(lldb.__version__)'
  ```
- Conda (cross-platform):
  ```bash
  conda install -c conda-forge lldb
  ```

If the import still fails, ensure you are using the Python that ships with (or can see) your LLDB installation.

We document known issues with older LLDB Python packages (e.g., LLDB 18 on some distros) and why the devcontainer installs LLDB 19 by default. See `docs/UNDER.md` for details and verification steps.

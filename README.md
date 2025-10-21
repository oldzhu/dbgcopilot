Debugger Copilot (POC)

Overview
--------
An AI-assisted debugger copilot for GDB (and later LLDB), focused on:
- Summarizing and analyzing command outputs
- Suggesting next debugging commands
- Goal-driven planning and optional auto mode

UX Summary
----------
- Single `copilot` command inside GDB opens a nested `copilot>` prompt.
- Natural language inputs go to the LLM; slash-commands control the session:
  - `/help`, `/new`, `/summary`, `/chatlog`, `/config`, `/exec <gdb-cmd>`, `/goal <text>`, `/llm list`, `/llm use <name>`
  - Natural prompts like "run the program" or "continue" are sent to the LLM; when it wants to execute something, it replies with `<cmd>the-gdb-command</cmd>` and the command runs automatically.

Current Status
--------------
- Installable package with a packaged GDB plugin: `dbgcopilot.plugins.gdb.copilot_cmd`
- Console helpers:
  - `dbgcopilot-plugin-path` prints the installed plugin file path
  - `dbgcopilot-gdb` launches GDB with the package available on `sys.path` and preloads the plugin by default
- Core scaffolding for orchestrator, state, and a GDB backend; default LLM provider is `openrouter`

Install and Build
-----------------
From the repo root in your Python 3.11+ venv:

```bash
make build
make install-wheel
```

Ways to load dbgcopilot in GDB
------------------------------
Pick whichever fits your workflow. All are supported.

1) Use the launcher (recommended)
- Starts GDB with `PYTHONPATH` pointing at the installed `site-packages` and preloads the plugin.

```bash
# import check
dbgcopilot-gdb -q -ex "python import dbgcopilot; print('IMPORTED')" -ex quit

# preload plugin (default); `copilot` will be available
dbgcopilot-gdb -q

# disable preload if you prefer manual import
dbgcopilot-gdb --no-preload -q -ex "python import dbgcopilot.plugins.gdb.copilot_cmd" \
  -ex copilot

# pass a program or corefile after --
dbgcopilot-gdb -- -q ./examples/crash_demo/crash
```

2) Import the packaged plugin inside GDB (no launcher)

```gdb
(gdb) python import dbgcopilot.plugins.gdb.copilot_cmd
(gdb) copilot
```

3) Source the packaged plugin (no launcher)

```bash
# In your shell, print the path once
dbgcopilot-plugin-path
# Copy that path and in GDB use:
(gdb) source /path/printed/by/dbgcopilot-plugin-path
```

4) Make GDB aware of your venv globally (optional)

Add to `~/.gdbinit` (or create a project-local `.gdbinit.local` you `source` at session start):

```gdb
python
import site
site.addsitedir('/workspace/.venv/lib/python3.12/site-packages')
end
```

Using the copilot prompt
------------------------
After the plugin is loaded:

```gdb
(gdb) copilot
[copilot] Entering copilot> (type '/help' or 'exit' to leave)
copilot> /help
copilot> /exec bt
copilot> why is this crashing?
copilot> /llm list
copilot> /llm use openrouter
copilot> /summary
copilot> /chatlog
copilot> exit
```

Notes
-----
- GDB runs an embedded Python that does not automatically use your venv. The launcher and the `~/.gdbinit` snippet above are convenient ways to make `import dbgcopilot` work consistently inside GDB.
- For quick tests, you can always rely on `python import dbgcopilot.plugins.gdb.copilot_cmd` inside GDB to register the `copilot` command.
- The assistant now uses an LLM-driven flow. If it decides to run a command, it will respond with `<cmd>…</cmd>` and the orchestrator executes it immediately. Otherwise, it answers normally.

Project Layout
--------------
- `src/dbgcopilot/` — package sources (core, llm, utils, plugins)
- `plugins/gdb/` — development-time plugin files
- `prompts/` — LLM prompt templates
- `configs/default.yaml` — defaults
- `tests/` — test stubs

License
-------
Apache-2.0 WITH LLVM-exception

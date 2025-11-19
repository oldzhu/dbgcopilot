# Loading Debugger Copilot in GDB

Pick whichever workflow fits:

1. **Use the launcher (recommended)** – Starts GDB with `PYTHONPATH` pointing at the installed `site-packages` and preloads the plugin.

```bash
# import check
dbgcopilot-gdb -q -ex "python import dbgcopilot; print('IMPORTED')" -ex quit

dbgcopilot-gdb -q

dbgcopilot-gdb --no-preload -q -ex "python import dbgcopilot.plugins.gdb.copilot_cmd" \
  -ex copilot

dbgcopilot-gdb -- -q ./examples/crash_demo/crash
```

2. **Import the packaged plugin inside GDB (no launcher)**

```gdb
(gdb) python import dbgcopilot.plugins.gdb.copilot_cmd
(gdb) copilot
```

3. **Source the packaged plugin (no launcher)**

```bash
# Print the path once
dbgcopilot-plugin-path
# In GDB:
(gdb) source /path/printed/by/dbgcopilot-plugin-path
```

4. **Make GDB aware of your venv globally (optional)**

Add to `~/.gdbinit` or a project-local `~/.gdbinit.local`:

```gdb
python
import site
site.addsitedir('/workspace/.venv/lib/python3.12/site-packages')
end
```

## Using the `copilot>` prompt

After the plugin is loaded:

```gdb
(gdb) copilot
[copilot] Entering copilot> (type '/help' or 'exit' to leave)
copilot> /help
copilot> /exec bt
copilot> why is this crashing?
copilot> /llm list
copilot> /llm use openrouter
copilot> /chatlog
copilot> exit
```

## Standalone copilot> (no debugger)

```bash
dbgcopilot
```

Inside the standalone REPL you can switch debuggers and commands:

```
copilot> /help
copilot> /use gdb
copilot> /exec help where
copilot> run the program until it crashes
copilot> /llm use openrouter
copilot> /llm key openrouter sk-...  # in-session only
copilot> quit
```

Using LLDB instead:

```
copilot> /use lldb
copilot> /exec version
copilot> /exec help thread backtrace
```

*Notes*:
- The GDB subprocess backend sets pagination/width/height for non-interactive output and disables confirm prompts.
- The LLDB path prefers the Python API backend (robust, prompt-free capture); it falls back to a subprocess backend that sets auto-confirm and a simple prompt when bindings are unavailable.
- The assistant proposes exactly one command at a time and only executes after it responds with `<cmd>…</cmd>`.

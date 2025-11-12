Debugger Copilot (POC)

Overview
--------
An AI-assisted debugger copilot for GDB, LLDB, Delve, Radare2, and pdb (Python debugger), focused on:
- Summarizing and analyzing command outputs
- Suggesting next debugging commands
- Goal-driven planning with human-in-the-loop confirmations

UX Summary
----------
- Single `copilot` command inside GDB opens a nested `copilot>` prompt.
- Natural language inputs go to the LLM; slash-commands control the session:
  - `/help`, `/new`, `/chatlog`, `/config`, `/exec <gdb-cmd>`, `/llm list`, `/llm use <name>`, `/colors on|off`
  - Natural prompts like "run the program" or "continue" are sent to the LLM; when it wants to execute something, it replies with `<cmd>the-gdb-command</cmd>` and the command runs automatically.
  - The REPL remains interactive-only. For autonomous runs, use the separate `dbgagent` CLI (see below).

Current Status
--------------
- Installable package with a packaged GDB plugin: `dbgcopilot.plugins.gdb.copilot_cmd`
- Console helpers:
  - `dbgcopilot-plugin-path` prints the installed plugin file path
  - `dbgcopilot-gdb` launches GDB with the package available on `sys.path` and preloads the plugin by default
  - `dbgcopilot` starts a standalone `copilot>` REPL (outside any debugger); pick `/use gdb` to spawn a GDB subprocess
  - LLDB (including a Rust-tuned flavor), Delve, Radare2, and pdb (Python debugger) backends are available in the standalone REPL via `/use <debugger>`
- Core scaffolding for orchestrator, state, and a GDB backend; default LLM provider is `openrouter`

Install and Build
-----------------
From the repo root in your Python 3.11+ venv:

```bash
make build
make install-wheel

# Optional: install the autonomous agent CLI
pip install -e dbgagent
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
copilot> /chatlog
copilot> exit
```

Standalone copilot> (no debugger)
---------------------------------
You can also start a standalone REPL without launching GDB yourself:

```bash
dbgcopilot
```

At the `copilot>` prompt, select a debugger and interact:

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

Notes:
- The GDB subprocess backend sets pagination/width/height for non-interactive output and disables confirm prompts.
- The LLDB path prefers the Python API backend (robust, prompt-free capture). If the Python bindings are not available, it falls back to a subprocess backend that sets auto-confirm and a simple prompt.
- The assistant proposes exactly one command at a time and only executes after it returns `<cmd>…</cmd>`.

Autonomous debugging (`dbgagent`)
---------------------------------
`dbgcopilot` stays focused on interactive, confirmation-driven workflows. For fully
automatic investigations, install the companion package that ships in this repository:

```bash
pip install -e dbgagent
DBGAGENT_LOG=1 dbgagent --debugger gdb --program ./examples/crash_demo/crash \
  --goal crash --llm-provider deepseek --llm-key "$DEEPSEEK_API_KEY"
```

`dbgagent` accepts command-line options for debugger selection, LLM provider/model,
API keys, goals (`crash|hang|leak|custom`) plus free-form text, and resume files. It
logs step-by-step execution to `/tmp` when `--log-session` (or `DBGAGENT_LOG`) is enabled
and always writes a Markdown report. Edit that report, add your own comments, and use
`--resume-from` to feed it back into a subsequent run for additional context.

LLM providers and configuration
-------------------------------
Available providers include:
- `openrouter` (default)
- Generic OpenAI-compatible: `openai-http` (custom endpoints), `ollama` (local), `llama-cpp` (local), and convenience aliases: `deepseek`, `qwen`, `kimi`, `glm`, `modelscope`

Quick start:
```
copilot> /llm list
copilot> /llm use deepseek
copilot> /llm key deepseek sk-...     # set API key for this session
copilot> /config                      # verify provider settings
```

Notes:
- OpenAI-compatible providers read `base_url`, `api_key`, `model`, and optional headers from the session config or environment. For convenience aliases we default to:
  - deepseek: base https://api.deepseek.com, model deepseek-chat
  - qwen (DashScope): base https://dashscope.aliyuncs.com (path /compatible-mode/v1/chat/completions), model qwen-turbo
  - kimi (Moonshot): base https://api.moonshot.cn, model moonshot-v1-8k
  - glm (ZhipuAI): base https://open.bigmodel.cn (path /api/paas/v4/chat/completions), model glm-4
  - llama-cpp: base http://localhost:8080 (llama.cpp server with --api), model llama
  - modelscope: base https://api-inference.modelscope.cn, model deepseek-ai/DeepSeek-R1-Distill-Llama-8B
- You can switch providers anytime with `/llm use <name>`.
- Colors are enabled by default; toggle with `/colors on|off`.

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
- `dbgagent/` — standalone autonomous agent package
- `examples/` — ready-made crash and hang scenarios for C/C++, Python, and Rust

Example Programs
----------------
- `examples/crash_demo` — original C crash demo bundled with a Makefile
- `examples/crash/python`, `examples/hang/python` — Python scripts for exception and hang scenarios (use the Python debugger backend)
- `examples/crash/rust`, `examples/hang/rust` — Cargo projects demonstrating a panic/segfault and an infinite loop

LLDB Python API (optional)
--------------------------
For the best LLDB experience, the standalone REPL will use the LLDB Python API to execute commands and capture output (similar to in-process LLDB). If the `lldb` Python module is not present, we automatically fall back to a subprocess backend.

Install the `lldb` Python module via your platform tools:

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

Background and notes:
- We document known issues with older LLDB Python packages (e.g., LLDB 18 on some distros) and why our devcontainer installs LLDB 19 by default.
- See `docs/UNDER.md` for details and verification steps.

License
-------
Apache-2.0 WITH LLVM-exception

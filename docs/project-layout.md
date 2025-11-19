# Project Layout & Example Programs

## Layout

- `src/dbgcopilot/` — package sources (core, llm, utils, plugins)
- `plugins/gdb/` — development-time plugin files
- `prompts/` — LLM prompt templates
- `configs/default.yaml` — defaults
- `tests/` — test stubs
- `src/dbgagent/` — standalone autonomous agent package
- `src/dbgweb/` — FastAPI-based debugger dashboard and APIs
- `examples/` — ready-made crash and hang scenarios for C/C++, Python, and Rust

## Example programs

- `examples/crash_demo` — original C crash demo bundled with a Makefile
- `examples/crash/python`, `examples/hang/python` — Python scripts for exception and hang scenarios (use the Python debugger backend)
- `examples/crash/java`, `examples/hang/java` — Java programs for panic/hang scenarios (use the jdb backend)
- `examples/crash/rust`, `examples/hang/rust` — Cargo projects demonstrating a panic/segfault and an infinite loop

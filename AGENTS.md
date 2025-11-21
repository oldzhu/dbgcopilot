# Agent Guidelines for Debugger Copilot Repository

This document provides standard guidance for AI agents and automated tools contributing changes to this repository. Following these guidelines helps ensure safe, minimal, and high-quality contributions.

## Repository overview

Debugger Copilot provides REPLs and backends for GDB/LLDB, with an LLM-driven orchestrator that suggests and runs debugger commands. Languages: Python (core, REPLs), a bit of shell/Make.

Key locations:
- `src/dbgcopilot/` — package sources (core, llm, utils, plugins)
- `plugins/` — development-time GDB/LLDB plugin integration
- `configs/` — configuration (prompts.json overrides, defaults)
- `tests/` — smoke tests
- `examples/` — simple programs for testing

## Build and test

- Build/install in a Python 3.11+ venv:
  - `make build`
  - `make install-wheel`
- Run tests: `pytest -q` (configured via `pyproject.toml`)
- Always activate the repo venv (`source .venv/bin/activate`) before running tests or tooling.
- Sanity run (optional):
  - Start standalone REPL: `dbgcopilot`
  - In REPL: `/use gdb` or `/use lldb`, then `/exec help where`

## Coding standards

- Python: follow PEP 8 and the existing code style; prefer small, focused functions; avoid introducing heavy dependencies.
- Keep changes minimal and surgical: prefer small diffs that address a single concern.
- Match surrounding patterns (naming, structure, error handling, logging/messages).
- Avoid leaking secrets; never add real keys to code or tests.

## Making changes

Before changes:
- Run a clean test: `pytest -q`.
- Skim related files and any prompt/config entries.

During changes:
- Preserve behavior unless a change is explicitly intended.
- Update tests or add a small smoke test when changing observable behavior.
- Prefer configuration toggles to hard-coded values.

After changes:
- Tests must pass locally: `pytest -q`.
- Verify basic REPL flows if relevant (`/use gdb|lldb`, `/exec bt`).
- Update docs if behavior/commands/configs changed.

## Actions (quick commands)

- Compile and package: `make build && make install-wheel`
- Run tests: `pytest -q`
- Lint (ad hoc): keep imports organized, avoid unused variables, respect existing style; run `python -m py_compile` on edited files if unsure.

## Project structure hints

- Orchestrator: `src/dbgcopilot/core/orchestrator.py` — prompt assembly, provider selection, interactive loop.
- Providers: `src/dbgcopilot/llm/*` — OpenRouter and OpenAI-compatible client and registry.
- REPLs: `src/dbgcopilot/repl/standalone.py`, `plugins/gdb/repl.py`, `plugins/lldb/repl.py` — slash commands and session config.
- Prompts: `src/dbgcopilot/prompts/` — defaults and tool instructions.
- Autonomous agent CLI: `src/dbgagent/` — standalone package that drives debugger commands automatically.

## Pull requests

- Title: concise summary of change.
- Description: what changed, why, and how to validate.
- Scope: keep PRs focused; unrelated refactors should be separate.
- Tests: include or update relevant tests where practical.

## Troubleshooting

- Missing dependencies: ensure `requests` and `pexpect` are installed (see `pyproject.toml`).
- LLDB Python API import issues: install `lldb` Python package or use subprocess backend.
- Provider errors: confirm API keys/base URLs in session config or environment.

## Notes for agentic tools

- Respect guardrails: do not modify unrelated files; avoid sweeping changes.
- Prefer additive changes; avoid breaking existing flows.
- If in doubt, propose changes via comments in PR description.

## Resources

- README.md for usage and quickstart
- configs/prompts.json for prompt overrides
- tests/test_smoke_structure.py for basic structure validation


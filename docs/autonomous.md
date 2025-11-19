# Autonomous Debugging (`dbgagent`)

`dbgcopilot` stays focused on interactive, confirmation-driven workflows. For fully automated investigations, install the companion CLI that ships in this repository:

```bash
pip install -e src/dbgagent
DBGAGENT_LOG=1 dbgagent --debugger gdb --program ./examples/crash_demo/crash \
  --goal crash --llm-provider deepseek --llm-key "$DEEPSEEK_API_KEY"
```

`dbgagent` accepts command-line options for debugger selection, LLM provider/model, API keys, goals (`crash|hang|leak|custom`), resume files, and language preferences. It logs step-by-step execution to `/tmp` when `--log-session` (or `DBGAGENT_LOG`) is enabled and always writes a Markdown report. Edit that report, add your own comments, and use `--resume-from` to feed it back into a subsequent run for additional context.

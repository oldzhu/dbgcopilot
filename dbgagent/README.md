# dbgagent

Autonomous debugging assistant built on top of the Debugger Copilot backends. The tool
runs GDB or LLDB commands automatically using an LLM provider and produces a final
report that can be edited and replayed in subsequent runs.

## Quick start

```bash
# Inside your virtual environment
pip install dbgcopilot  # install the shared backends and providers
pip install -e dbgagent

# Investigate a crash automatically using DeepSeek
DBGAGENT_LOG=1 dbgagent --debugger gdb --program ./examples/crash_demo/crash \
    --goal crash --llm-provider deepseek --llm-key "$DEEPSEEK_API_KEY"

# Force English responses (default) or switch to Simplified Chinese
dbgagent --language en ...
dbgagent --language zh ...
```

The agent records its actions in a plaintext log (when `--log-session` or `DBGAGENT_LOG` is
set) and writes the final report to `/tmp` unless overridden via `--report-file`. You can
hand-edit the report and pass it back to the agent with `--resume-from` to continue the
analysis with additional notes. When `--debugger lldb` is selected, dbgagent uses the LLDB
Python API directly (falling back to the subprocess backend only if the API is unavailable).
Each run records the chosen backend plus LLM token usage and, when available, provider-reported
costs in both the session log and the generated report.

# Installation & Build

From the repo root in your Python 3.11+ virtual environment:

```bash
make build
make install-wheel

# Optional: install the autonomous agent CLI
pip install -e src/dbgagent
```

The editable install keeps the `dbgagent` executable pointing to `src/dbgagent`. If you move or edit those sources, rerun the editable install so the console script resolves correctly.

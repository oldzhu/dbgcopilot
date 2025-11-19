# Installation & Build

From the repo root in your Python 3.11+ virtual environment:

```bash
make build
make install-wheel

# Optional: install the autonomous agent CLI
pip install -e src/dbgagent
```

The editable install keeps the `dbgagent` executable pointing to `src/dbgagent`. If you move or edit those sources, rerun the editable install so the console script resolves correctly.

If you prefer to install from the built wheels instead of editable sources, build both packages and install them directly:

```bash
# from repo root
python -m build  # produces dist/dbgcopilot-*.whl
cd src/dbgagent
python -m build  # produces src/dbgagent/dist/dbgagent-*.whl
cd -
pip install dist/dbgcopilot-<version>-py3-none-any.whl
pip install src/dbgagent/dist/dbgagent-<version>-py3-none-any.whl
```

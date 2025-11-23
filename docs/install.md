# Installation & Testing (end-user guide)

This guide walks through installing the published packages rather than building from source. If you need to contribute or develop locally, the previous sections still live in the project README/Makefile.

## Prerequisites
- Python 3.11 or newer (Ubuntu 22.04 ships 3.10; install a newer interpreter or use `pyenv`).
- native debugger tooling: GDB, LLDB, Delve, Radare2, Rust toolchain, Go/Delve, and a headless JDK for `jdb`. The [`Dockerfile`](../Dockerfile) documents the exact packages we include in the dev image and contains the commands used to set up the supported debuggers.
- Optional helper utilities: `pip`, `virtualenv`, `curl`.

Both `dbgcopilot` and `dbgagent` print a reminder about missing debugger binaries (and link back to this section) when the runtime checks detect that those tools are not on `PATH`.

## Install from GitHub
Install the published GitHub-release wheels so you get the console scripts for `dbgcopilot`, `dbgagent`, and the `dbgweb` FastAPI dashboard. Since the PyPI wheels have not been published yet, download the release assets directly until the pip upload lands.

```bash
python -m venv ~/.dbgcopilot
source ~/.dbgcopilot/bin/activate
python -m pip install --upgrade pip
pip install https://github.com/oldzhu/dbgcopilot/releases/download/<release>/dbgcopilot-<version>-py3-none-any.whl
pip install https://github.com/oldzhu/dbgcopilot/releases/download/<release>/dbgagent-<version>-py3-none-any.whl
```

If you are testing a prerelease, download the wheel assets from the GitHub release and install them directly:

```bash
pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgcopilot-0.0.1-py3-none-any.whl
pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgagent-0.0.1-py3-none-any.whl
```

## Install from PyPI (pending)
The PyPI wheels have not been published yet. Once the release goes live you can switch to the usual pip workflow using the same package names:

```bash
pip install dbgcopilot==<version>
pip install dbgagent==<version>
```
Keep an eye on the release notes; the PyPI wheels will include the same scripts and entry points as the GitHub assets.

## Quick verification
- `dbgcopilot --help` should launch the REPL instructions.
- `dbgagent --help` should display the autonomous agent CLI options.
- Start the FastAPI dashboard if desired:
	```bash
	uvicorn dbgweb.app.main:app --reload --port 8080
	```
- Run the smoke test bundle (optional but recommended):
	```bash
	python -m pytest tests/test_smoke_structure.py
	```
	The tests make sure the package exports the console scripts and plugin entry points correctly.

## Additional ways to use & test

### Clone + Dev Container
Clone the repo, open it in VS Code (with Remote-Containers) or use the `devcontainer` CLI so you get the same image above. Inside that environment you can rebuild/install/test just like the developer workflow but without manual dependency installation:

```bash
docker pull oldzhu/dbgcopilot-dev:latest
docker run --rm -it -v "$PWD":/workspace -w /workspace oldzhu/dbgcopilot-dev:latest bash
# Inside the container run the familiar commands:
dbgcopilot --help
dbgagent --help
python -m pytest tests/test_smoke_structure.py
```

### Docker image (pending publication)
The published Docker image (`oldzhu/dbgcopilot-dev:latest`) is not available yet. Once it ships, you can skip installing Python packages locally by pulling and running the container while mounting whatever workspace or examples you want to exercise:

```bash
git clone https://github.com/oldzhu/dbgcopilot.git
cd dbgcopilot
# The dev container pre-installs the toolchain; rebuild the wheels if you prefer:
python -m build
cd src/dbgagent && python -m build
cd -
pip install --upgrade dist/dbgcopilot-*.whl
pip install --upgrade src/dbgagent/dist/dbgagent-*.whl
dbgcopilot --help
dbgagent --help
python -m pytest tests/test_smoke_structure.py
```
You can also install `dbgagent` in editable mode (`pip install -e src/dbgagent`) when hacking on the CLI itself.

## Summary
This environment now mirrors what end users experience when they install the pip release. For developer workflows or publishing steps, see [`README.md`](../README.md) and [`docs/publishing.md`](publishing.md).

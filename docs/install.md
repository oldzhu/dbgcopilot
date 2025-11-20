# Installation & Testing (end-user guide)

This guide walks through installing the published packages rather than building from source. If you need to contribute or develop locally, the previous sections still live in the project README/Makefile.

## Prerequisites
- Python 3.11 or newer (Ubuntu 22.04 ships 3.10; install a newer interpreter or use `pyenv`).
- native debugger tooling: GDB, LLDB, Delve, Radare2, Rust toolchain, Go/Delve, and a headless JDK for `jdb`. The [`Dockerfile`](../Dockerfile) documents the exact packages we include in the dev image.
- Optional helper utilities: `pip`, `virtualenv`, `curl`.

## Install from PyPI or GitHub
Install the published wheels for both packages so you get the console scripts for `dbgcopilot`, `dbgagent`, and the FastAPI dashboard.

```bash
python -m venv ~/.dbgcopilot
source ~/.dbgcopilot/bin/activate
python -m pip install --upgrade pip
pip install dbgcopilot==<version>
pip install dbgagent==<version>
```

If you are testing a prerelease, download the wheel assets from the GitHub release and install them directly:

```bash
pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgcopilot-0.0.1-py3-none-any.whl
pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgagent-0.0.1-py3-none-any.whl
```

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

### Docker image
When the published image (for example `oldzhu/dbgcopilot-dev:latest`) is available, you can skip installing Python packages locally. Pull and run the container, mounting whatever workspace or examples you want to exercise:

```bash
docker pull oldzhu/dbgcopilot-dev:latest
docker run --rm -it -v "$PWD":/workspace -w /workspace oldzhu/dbgcopilot-dev:latest bash
# Inside the container run the familiar commands:
dbgcopilot --help
dbgagent --help
python -m pytest tests/test_smoke_structure.py
```

### Clone + Dev Container
Clone the repo, open it in VS Code (with Remote-Containers) or use the `devcontainer` CLI so you get the same image above. Inside that environment you can rebuild/install/test just like the developer workflow but without manual dependency installation:

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

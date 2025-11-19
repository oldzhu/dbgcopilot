# Distribution & Publishing

End users can try the project through one of three delivery channels while we publish the artifacts:

1. **pip package** – publish `dbgcopilot` (plus `dbgagent`/`dbgweb`) to PyPI. Users simply run `pip install dbgcopilot` and `pip install -e src/dbgagent` locally, but they must also install the debugger toolchain that powers the autonomous flows. The [`Dockerfile`](../Dockerfile) already enumerates the expected dependencies (GDB, LLDB, Delve, Radare2, the Rust toolchain, Go/Delve, and a headless JDK for `jdb`). Make sure your system ships those binaries or install them via your distro before running `dbgagent` or the REPL.
2. **Docker Hub image** – ship a container (e.g., `oldzhu/dbgcopilot-dev:latest`) that already includes the tools and Python packages. Build with `docker build -t dbgcopilot-dev:latest .`, tag it (`docker tag ... oldzhu/dbgcopilot-dev:latest`), and push (`docker push oldzhu/dbgcopilot-dev:latest`). Users can then run the published image, mount their workspace, and execute commands such as `python -m pytest -q` or the `dbgagent` CLI inside the container.
3. **Dev Container** – clone the repo and use the `.devcontainer/devcontainer.json` definition with VS Code Remote-Containers or the `devcontainer` CLI. The dev container mirrors the Docker Hub image, exposes proxy arguments via `remoteEnv`, and provides commands such as `make docker-build`, `make docker-pytest`, and the various `gdb`/`lldb` helper targets described later in this README.

## GitHub prerelease workflow

1. Build the distributables for the version you intend to ship:
   ```bash
   cd /workspace
   python -m build
   ```
   This drops `dbgcopilot-<version>.whl` and `.tar.gz` into `dist/`.
2. Create a Git tag (for example `v0.0.1-pre`) and push it to GitHub:
   ```bash
   git tag v0.0.1-pre
   git push origin v0.0.1-pre
   ```
3. Draft a GitHub release (via the web UI or `gh release create`) and mark it as a **pre-release**. Attach the wheel/tarball assets from the `dist/` directory:
   ```bash
   gh release create v0.0.1-pre dist/dbgcopilot-0.0.1-py3-none-any.whl dist/dbgcopilot-0.0.1.tar.gz \
     --prerelease --title "v0.0.1-pre" --notes "Pre-release for early testing"
   ```
4. Document in the release notes that testers should install the wheel directly from GitHub and that the system-level debugger toolchain (GDB, LLDB, Delve, Radare2, Rust/Go toolchains, JDK) must still be installed manually.
5. Share the raw download URLs with testers so they can install the wheel:
   ```bash
   pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgcopilot-0.0.1-py3-none-any.whl
   ```
6. Ask testers to exercise the CLI quickly after installation:
   ```bash
   dbgcopilot --help
   dbgagent --help
   python -m pytest tests/test_smoke_structure.py
   ```
   These commands confirm the scripts load, any external network/dependency requirements are satisfied, and the smoke test passes prior to the official PyPI publish.

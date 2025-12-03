# Distribution & Publishing

End users can try the project through one of three delivery channels while we publish the artifacts. Because `dbgagent` ships as its own package on top of the shared `dbgcopilot` backends, we publish/install two wheels (`dbgcopilot` and `dbgagent`) so both console scripts (`dbgcopilot`/`dbgagent`) are available.

1. **pip package** – publish both the shared `dbgcopilot` wheel and the standalone `dbgagent` wheel to PyPI. Users can install them via `pip install dbgcopilot==<version>` and `pip install dbgagent==<version>` (or wheel URLs). Both packages rely on the debugger tooling described in the [`Dockerfile`](../Dockerfile) (GDB, LLDB, Delve, Radare2, Rust, Go/Delve, JDK). Ensure those tools are present before running `dbgagent` or the REPL.
2. **Docker Hub image** – ship a container (e.g., `oldzhu/dbgcopilot-dev:latest`) that already includes the tools and Python packages. Build with `docker build -t dbgcopilot-dev:latest .`, tag it (`docker tag ... oldzhu/dbgcopilot-dev:latest`), and push (`docker push oldzhu/dbgcopilot-dev:latest`). Users can then run the published image, mount their workspace, and execute commands such as `python -m pytest -q` or the `dbgagent` CLI inside the container.
3. **Dev Container** – clone the repo and use the `.devcontainer/devcontainer.json` definition with VS Code Remote-Containers or the `devcontainer` CLI. The dev container mirrors the Docker Hub image, exposes proxy arguments via `remoteEnv`, and provides commands such as `make docker-build`, `make docker-pytest`, and the various `gdb`/`lldb` helper targets described later in this README.

## GitHub prerelease workflow

1. Build the distributables for the version you intend to ship. Producing both wheels requires building at the repo root and inside `src/dbgagent`:
   ```bash
   cd /workspace
   python -m build                      # creates dist/dbgcopilot-<version>.whl
   cd src/dbgagent
   python -m build                      # creates src/dbgagent/dist/dbgagent-<version>.whl
   cd -
   ```
   This drops `dbgcopilot-<version>.whl`/`.tar.gz` into `dist/` and `dbgagent-<version>.whl` into `src/dbgagent/dist/`.
2. Create a Git tag (for example `v0.0.1-pre`) and push it to GitHub:
   ```bash
   git tag v0.0.1-pre
   git push origin v0.0.1-pre
   ```
3. Draft a GitHub release (via the web UI or `gh release create`) and mark it as a **pre-release**. Attach both wheel assets (and the source tarball) so testers can pip-install each package:
    ```bash
    gh release create v0.0.1-pre dist/dbgcopilot-0.0.1-py3-none-any.whl dist/dbgcopilot-0.0.1.tar.gz \
       src/dbgagent/dist/dbgagent-0.0.1-py3-none-any.whl \
       Dockerfile docker-compose.yml \
       --prerelease --title "v0.0.1-pre" --notes "Pre-release for early testing"
    ```
   Also include the `Dockerfile`/`docker-compose.yml` used to build the image so testers can download the artifacts and run `docker build` or `docker compose build` themselves while the published image is pending.
4. Document in the release notes that testers should install the wheel directly from GitHub and that the system-level debugger toolchain (GDB, LLDB, Delve, Radare2, Rust/Go toolchains, JDK) must still be installed manually. The dev container already ships with `gh`, so you can run `gh release create ...` directly inside it.
5. Share the raw download URLs with testers so they can install both wheels:
   ```bash
   pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgcopilot-0.0.1-py3-none-any.whl
   pip install https://github.com/oldzhu/dbgcopilot/releases/download/v0.0.1-pre/dbgagent-0.0.1-py3-none-any.whl
   ```
6. Ask testers to exercise the CLI quickly after installation:
   ```bash
   dbgcopilot --help
   dbgagent --help
   python -m pytest tests/test_smoke_structure.py
   ```
   These commands confirm the scripts load, any external network/dependency requirements are satisfied, and the smoke test passes prior to the official PyPI publish.

# Under notes

This document tracks a few running notes about environment choices and known issues.

## Why we install LLDB 19 in the devcontainer

Context:
- On Ubuntu 24.04 with the stock LLVM/LLDB 18 packages, importing the Python module `lldb` from a standalone Python interpreter can fail or crash in certain configurations.
- Symptoms include:
  - `ModuleNotFoundError: No module named '_lldb'`
  - `ImportError: cannot import name '_lldb' from partially initialized module 'lldb'`
  - Fatal error: `PyImport_AppendInittab() may not be called after Py_Initialize()`
- Root cause: a combination of packaging and initialization paths affecting the Python bindings in LLDB 18. The upstream issue was resolved in newer LLDB versions.
- Reference: llvm/llvm-project#70453

Decision:
- We install LLDB 19 (lldb-19, python3-lldb-19, liblldb-19) in the devcontainer image. This eliminates the class of import problems present with 18.x and gives us a more reliable base for testing the LLDB subprocess backend.

How we install LLDB 19:
- The base image is `mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04` (Noble).
- We add the apt.llvm.org repository for LLVM/LLDB 19 and install:
  - `lldb-19`
  - `python3-lldb-19`
  - `liblldb-19`
- We symlink `/usr/bin/lldb` to `/usr/bin/lldb-19` so `lldb` resolves to 19 by default.

Verification steps:
- Confirm LLDB version and Python path:
  - `lldb --version`
  - `lldb -P`
- Verify Python import (standalone):
  - `PYTHONPATH="$(lldb -P)" python3 -c "import lldb; print('OK', lldb.__file__)"`
- In our REPL (`dbgcopilot`):
  - `/use lldb`
  - On success: `[copilot] Using LLDB (API backend).`
  - If API import is unsafe, the REPL will fall back to the subprocess backend with a hint.

Notes:
- The codepath for LLDB Python API import is conservative: it probes in a short subprocess first. If the probe fails or crashes, we avoid importing in the main process and use the subprocess backend instead.
- You can force the subprocess backend by setting `DBGCOPILOT_LLDB_API=0`.

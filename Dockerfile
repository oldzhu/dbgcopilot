# Dev container for Debugger Copilot POC
# Use DevContainers C++ image with gcc/clang/gdb preinstalled
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Note: cpp image already contains build-essential, gcc/g++, cmake, ninja, clang, gdb.
# lldb may not be present; we will add it later once network issues are resolved.

WORKDIR /workspace

# Ensure LLDB and pytest are available without relying on pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    lldb python3-pytest python3-pip python3-setuptools python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Ensure pip is up-to-date so `python3 -m pip` works in the devcontainer postCreateCommand
RUN python3 -m pip install --upgrade pip setuptools wheel || true

# Default command: drop into bash
CMD ["bash"]

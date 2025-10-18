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
    lldb python3-pytest \
    && rm -rf /var/lib/apt/lists/*

# Default command: drop into bash
CMD ["bash"]

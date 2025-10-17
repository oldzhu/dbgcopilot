# Dev container for Debugger Copilot POC
# Use DevContainers C++ image with gcc/clang/gdb preinstalled
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Note: cpp image already contains build-essential, gcc/g++, cmake, ninja, clang, gdb.
# lldb may not be present; we will add it later once network issues are resolved.

WORKDIR /workspace

# Install Python test tooling globally in container (no local venv required)
RUN pip3 install --no-cache-dir pytest

# Default command: drop into bash
CMD ["bash"]

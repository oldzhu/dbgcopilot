# Dev container for Debugger Copilot POC
# Use DevContainers C++ image with gcc/clang/gdb preinstalled
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Note: cpp image already contains build-essential, gcc/g++, cmake, ninja, clang, gdb.
# lldb may not be present; we will add it later once network issues are resolved.

WORKDIR /workspace

# Base tools; install pytest/pip/venv now. We'll install a newer LLDB below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pytest python3-pip python3-setuptools python3-venv gnupg wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install LLVM/LLDB 19 from apt.llvm.org (Ubuntu 24.04 = noble)
# Ref: https://apt.llvm.org/
RUN set -eux; \
    echo "Adding apt.llvm.org repo for LLVM/LLDB 19"; \
    wget -O- https://apt.llvm.org/llvm-snapshot.gpg.key | gpg --dearmor | tee /usr/share/keyrings/llvm-snapshot.gpg >/dev/null; \
    echo "deb [signed-by=/usr/share/keyrings/llvm-snapshot.gpg] http://apt.llvm.org/noble/ llvm-toolchain-noble-19 main" > /etc/apt/sources.list.d/llvm-19.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends lldb-19 python3-lldb-19 liblldb-19 liblldb-19-dev; \
    ln -sf /usr/bin/lldb-19 /usr/bin/lldb; \
    rm -rf /var/lib/apt/lists/*

# Ensure pip is up-to-date so `python3 -m pip` works in the devcontainer postCreateCommand
RUN python3 -m pip install --upgrade pip setuptools wheel || true

# Default command: drop into bash
CMD ["bash"]

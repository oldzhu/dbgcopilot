# Dev container for Debugger Copilot POC
# Use DevContainers C++ image with gcc/clang/gdb preinstalled
FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

ENV GOROOT=/usr/local/go \
    GOPATH=/opt/go \
    RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="${GOROOT}/bin:${GOPATH}/bin:${CARGO_HOME}/bin:${PATH}"

# Note: cpp image already contains build-essential, gcc/g++, cmake, ninja, clang, gdb.
# lldb may not be present; we will add it later once network issues are resolved.

WORKDIR /workspace

# Base tools; install pytest/pip/venv now. We'll install a newer LLDB below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pytest python3-pip python3-setuptools python3-venv gnupg curl wget ca-certificates \
    git make pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Go toolchain manually (apt pkg unavailable) and Delve debugger
RUN wget -q -O /tmp/go.tar.gz https://go.dev/dl/go1.25.4.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm -f /tmp/go.tar.gz \
    && mkdir -p ${GOPATH} \
    && go install github.com/go-delve/delve/cmd/dlv@latest

# Install latest radare2 from upstream
RUN git clone --depth=1 https://github.com/radareorg/radare2.git /opt/radare2 \
    && /opt/radare2/sys/install.sh \
    && rm -rf /opt/radare2

# Install Rust toolchain via rustup (stable channel, minimal profile)
RUN set -eux; \
    curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable; \
    chmod -R a+rX ${RUSTUP_HOME} ${CARGO_HOME}; \
    rustup component add rustfmt clippy

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

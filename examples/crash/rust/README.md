# Rust Crash Example

A minimal Cargo project that intentionally dereferences a null pointer to trigger a segmentation fault.

## Build

```bash
cargo build
```

The resulting binary will be at `target/debug/rust_crash`.

## Debugging with Debugger Copilot

1. Build the project so the binary exists.
2. Select the `LLDB (Rust)` debugger.
3. Set the **Program** field to `target/debug/rust_crash`.
4. Start a session and inspect the fault with Copilot.

# Rust Hang Example

A simple program that loops forever, useful for demonstrating attach/pause inspections.

## Build

```bash
cargo build
```

Binary location: `target/debug/rust_hang`.

## Debugging with Debugger Copilot

1. Build the project.
2. Choose the `LLDB (Rust)` debugger.
3. Point the **Program** field to `target/debug/rust_hang`.
4. Start a session, continue the program, then pause/inspect as needed.

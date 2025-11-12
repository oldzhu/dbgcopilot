# Java Crash Example

A minimal Java program that dereferences a `null` value to demonstrate debugging
with the `jdb` backend.

## Compile

```bash
javac -g Crash.java
```

## Run directly

```bash
java Crash
```

## Debug with Debugger Copilot

1. Set the debugger to `jdb (Java debugger)`.
2. Point the **Program** field to `Crash.java`, or leave it compiled and point to `Crash.class`.
3. Start the session and let the copilot inspect the exception.
```
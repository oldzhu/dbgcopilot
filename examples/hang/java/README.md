# Java Hang Example

A Java program that sleeps inside an infinite loop so you can practice
interrupting and inspecting threads with `jdb`.

## Compile

```bash
javac -g Hang.java
```

## Run directly

```bash
java Hang
```

## Debug with Debugger Copilot

1. Select `jdb (Java debugger)` as the debugger.
2. Point the **Program** field to `Hang.java` or the compiled `Hang.class`.
3. Start a session and use the copilot to pause execution, inspect threads, and resume.

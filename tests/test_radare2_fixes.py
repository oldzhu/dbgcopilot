#!/usr/bin/env python3
"""Quick test script for radare2 backend fixes."""
import sys
sys.path.insert(0, "/workspace/src")

from dbgcopilot.backends.radare2_subprocess import Radare2SubprocessBackend

# Test 1: Color output
print("=== Test 1: Color output ===")
backend = Radare2SubprocessBackend("/workspace/examples/bin/c/crash")
backend.initialize_session()
print(f"Startup: {backend.startup_output}")
output = backend.run_command("pd 5 @ entry0")
print(f"Output length: {len(output)}")
print(f"Contains ANSI codes: {chr(27) in output}")
print("First 300 chars of output:")
print(repr(output[:300]))
print()

# Test 2: Single execution (no double output)
print("=== Test 2: Single command execution ===")
output2 = backend.run_command("pdf @ sym.boom")
lines = output2.strip().split('\n')
print(f"Number of output lines: {len(lines)}")
print("Output:")
print(output2)
print()

# Test 3: Invalid command
print("=== Test 3: Invalid command (should see error once) ===")
output3 = backend.run_command("pdf @ nonexistent")
print("Output:")
print(output3)
error_lines = [l for l in output3.split('\n') if 'ERROR' in l]
print(f"Number of ERROR lines: {len(error_lines)}")

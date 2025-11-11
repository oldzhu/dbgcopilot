"""Python debugging backend powered by debugpy.

Provides a minimal command-oriented interface that mirrors the style of the
existing GDB/LLDB backends so the orchestrator can drive Python sessions using
simple textual commands (run, continue, bt, print, etc.).
"""
from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class _DAPClient:
    """Lightweight Debug Adapter Protocol client for debugpy."""

    def __init__(self, host: str, port: int) -> None:
        self._sock = socket.create_connection((host, port))
        self._lock = threading.Lock()
        self._seq = 1
        self._responses: Dict[int, Dict[str, Any]] = {}
        self._cond = threading.Condition()
        self._closed = False
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._buffered_events: Dict[str, queue.SimpleQueue[Dict[str, Any]]] = {}
        self._output_lock = threading.Lock()
        self._output_chunks: list[str] = []
        self._reader.start()

    def close(self) -> None:
        self._closed = True
        try:
            self._sock.close()
        except Exception:
            pass

    def send_request(
        self,
        command: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        seq = self.send_request_no_wait(command, arguments)
        return self.wait_for_response(seq, timeout=timeout)

    def send_request_no_wait(
        self,
        command: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> int:
        payload: Dict[str, Any] = {
            "type": "request",
            "seq": self._next_seq(),
            "command": command,
        }
        if arguments is not None:
            payload["arguments"] = arguments
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._lock:
            self._sock.sendall(header + data)
        return payload["seq"]

    def wait_for_response(self, seq: int, timeout: float | None = 10.0) -> Dict[str, Any]:
        if seq <= 0:
            raise ValueError("invalid request sequence")
        deadline = time.monotonic() + timeout if timeout else None
        with self._cond:
            while True:
                if seq in self._responses:
                    message = self._responses.pop(seq)
                    return message
                if self._closed:
                    raise RuntimeError("debugpy connection closed")
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"Timed out waiting for response seq {seq}")
                self._cond.wait(timeout=remaining)

    def wait_for_event(self, event_type: Optional[str] = None, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        if event_type:
            buffered = self._buffered_events.get(event_type)
            if buffered and not buffered.empty():
                return buffered.get()
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
            try:
                message = self._event_queue.get(timeout=remaining)
            except queue.Empty:
                return None
            if event_type is None or message.get("event") == event_type:
                return message
            buffered = self._buffered_events.setdefault(message.get("event", ""), queue.SimpleQueue())
            buffered.put(message)

    def drain_output(self) -> str:
        with self._output_lock:
            if not self._output_chunks:
                return ""
            text = "".join(self._output_chunks)
            self._output_chunks.clear()
            return text

    def _next_seq(self) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            return seq

    def _reader_loop(self) -> None:  # pragma: no cover - network/IO heavy
        buffer = b""
        try:
            while not self._closed:
                while b"\r\n\r\n" not in buffer:
                    chunk = self._sock.recv(4096)
                    if not chunk:
                        self._closed = True
                        with self._cond:
                            self._cond.notify_all()
                        return
                    buffer += chunk
                header, buffer = buffer.split(b"\r\n\r\n", 1)
                length = None
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        try:
                            length = int(line.split(b":", 1)[1].strip())
                        except Exception:
                            length = None
                        break
                if length is None:
                    continue
                while len(buffer) < length:
                    chunk = self._sock.recv(length - len(buffer))
                    if not chunk:
                        self._closed = True
                        with self._cond:
                            self._cond.notify_all()
                        return
                    buffer += chunk
                body = buffer[:length]
                buffer = buffer[length:]
                try:
                    message = json.loads(body.decode("utf-8"))
                except Exception:
                    continue
                mtype = message.get("type")
                if mtype == "response":
                    req_seq = message.get("request_seq")
                    with self._cond:
                        if isinstance(req_seq, int):
                            self._responses[req_seq] = message
                        self._cond.notify_all()
                    continue
                if mtype == "event":
                    event = message.get("event")
                    if event == "output":
                        text = message.get("body", {}).get("output", "")
                        if text:
                            with self._output_lock:
                                self._output_chunks.append(text)
                        continue
                    self._event_queue.put(message)
        finally:
            self._closed = True
            with self._cond:
                self._cond.notify_all()


class PythonDebugpyBackend:
    name = "python"
    prompt = "(pydbg)"

    def __init__(self, program: Optional[str] = None, python_path: Optional[str] = None, cwd: Optional[str] = None) -> None:
        self.python_path = python_path or sys.executable
        self.program: Optional[str] = program
        self.cwd = cwd
        self._listen_host = "127.0.0.1"
        self._listen_port: Optional[int] = None
        self._process: Optional[subprocess.Popen[str]] = None
        self._dap: Optional[_DAPClient] = None
        self._current_thread: Optional[int] = None
        self._current_frame: Optional[int] = None
        self._last_stop_reason: Optional[str] = None
        self._last_exit_code: Optional[int] = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def initialize_session(self) -> None:
        try:
            import importlib

            importlib.import_module("debugpy")
        except Exception as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "debugpy is required for the Python backend. Install it with 'pip install debugpy'."
            ) from exc

    def close(self) -> None:
        try:
            if self._dap:
                try:
                    self._dap.send_request("disconnect", {"terminateDebuggee": True}, timeout=2.0)
                except Exception:
                    pass
                self._dap.close()
        finally:
            self._dap = None
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
            try:
                self._process.wait(timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        self._current_thread = None
        self._current_frame = None
        self._last_stop_reason = None
        self._last_exit_code = None

    # ------------------------------------------------------------------
    # Command handling
    def run_command(self, cmd: str, timeout: float | None = None) -> str:
        command = (cmd or "").strip()
        if not command:
            return ""
        if command.lower().startswith("file "):
            path = command[5:].strip()
            if not path:
                return "[python] provide a script path"
            resolved = self._resolve_program_path(path)
            self.program = resolved
            return f"[python] script set to {resolved}"
        if command.lower() in {"run", "r"}:
            return self._handle_run()
        if command.lower() in {"quit", "q"}:
            self.close()
            return "[python] session terminated"
        if not self._dap:
            return "[python] no program is running. Use 'file <script.py>' and 'run'."
        if command.lower() in {"continue", "c"}:
            return self._handle_continue()
        if command.lower() in {"next", "n"}:
            return self._handle_step("next")
        if command.lower() in {"step", "s", "stepin"}:
            return self._handle_step("stepIn")
        if command.lower() in {"where", "bt", "backtrace"}:
            return self._render_stack()
        if command.lower().startswith("print ") or command.lower().startswith("p "):
            expr = command.split(" ", 1)[1].strip()
            return self._handle_evaluate(expr)
        if command.lower().startswith("info locals"):
            return self._handle_locals()
        return f"[python] unsupported command: {command}"

    # ------------------------------------------------------------------
    # Helpers
    def _resolve_program_path(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            if self.cwd:
                p = Path(self.cwd) / p
            else:
                p = Path.cwd() / p
        return str(p.resolve())

    def _handle_run(self) -> str:
        if not self.program:
            return "[python] no script configured. Use 'file <script.py>' first."
        self.close()
        port = self._pick_port()
        self._listen_port = port
        cmd = [self.python_path, "-m", "debugpy", "--listen", f"{self._listen_host}:{port}", "--wait-for-client", self.program]
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.cwd or os.path.dirname(self.program),
                text=True,
            )
        except FileNotFoundError as exc:
            return f"[python] failed to start python interpreter: {exc}"
        except Exception as exc:
            return f"[python] failed to launch script: {exc}"

        try:
            client = self._connect_debugpy(port)
        except Exception as exc:
            self.close()
            return f"[python] unable to connect to debugpy: {exc}"
        self._dap = client
        try:
            init_response = self._dap.send_request(
                "initialize",
                {
                    "clientID": "dbgcopilot",
                    "clientName": "Debugger Copilot",
                    "adapterID": "python",
                    "pathFormat": "path",
                    "supportsProgressReporting": False,
                    "supportsVariableType": True,
                },
            )
            if not init_response.get("success", False):
                message = init_response.get("message") or init_response.get("body", {}).get("error")
                raise RuntimeError(f"initialize failed: {message}")

            attach_args: Dict[str, Any] = {
                "justMyCode": False,
                "stopOnEntry": True,
                "redirectOutput": True,
            }
            attach_seq = self._dap.send_request_no_wait("attach", attach_args)

            # debugpy emits an ``initialized`` event once it has finished preparing the session.
            self._dap.wait_for_event("initialized", timeout=10.0)
            self._dap.send_request("configurationDone", {}, timeout=5.0)
            attach_response = self._dap.wait_for_response(attach_seq, timeout=5.0)
            if not attach_response.get("success", False):
                message = attach_response.get("message") or attach_response.get("body", {}).get("error")
                raise RuntimeError(f"attach failed: {message}")
        except Exception as exc:
            self.close()
            return f"[python] debugpy handshake failed: {exc}"

        event = self._dap.wait_for_event(timeout=10.0)
        output = self._dap.drain_output()
        io_text = output.strip()
        pieces: list[str] = []
        if io_text:
            pieces.append(io_text)

        if not event:
            pieces.append("[python] program running...")
            return "\n".join(pieces)

        etype = event.get("event")
        if etype == "stopped":
            pieces.append(self._describe_stop(event))
            return "\n".join(filter(None, pieces))
        if etype in {"terminated", "exited"}:
            self._record_exit(event)
            pieces.append(self._format_exit_message())
            return "\n".join(filter(None, pieces))

        # Unexpected event type; capture for debugging and continue.
        pieces.append(f"[python] received event: {etype}")
        return "\n".join(filter(None, pieces))

    def _handle_continue(self) -> str:
        if not self._dap or not self._current_thread:
            return "[python] no active stop to continue from"
        try:
            self._dap.send_request("continue", {"threadId": self._current_thread})
        except Exception as exc:
            return f"[python] continue failed: {exc}"
        event = self._dap.wait_for_event(timeout=30.0)
        output = self._dap.drain_output()
        pieces: list[str] = []
        stripped = output.strip()
        if stripped:
            pieces.append(stripped)
        if not event:
            pieces.append("[python] program running...")
            return "\n".join(pieces)
        etype = event.get("event")
        if etype == "stopped":
            pieces.append(self._describe_stop(event))
            return "\n".join(filter(None, pieces))
        if etype in {"terminated", "exited"}:
            self._record_exit(event)
            pieces.append(self._format_exit_message())
            return "\n".join(filter(None, pieces))
        # Unexpected event - stash and inform user
        pieces.append(f"[python] received event: {etype}")
        return "\n".join(filter(None, pieces))

    def _handle_step(self, command: str) -> str:
        if not self._dap or not self._current_thread:
            return "[python] no active stop to step from"
        try:
            self._dap.send_request(command, {"threadId": self._current_thread})
        except Exception as exc:
            return f"[python] step failed: {exc}"
        event = self._dap.wait_for_event("stopped", timeout=10.0)
        output = self._dap.drain_output()
        pieces: list[str] = []
        stripped = output.strip()
        if stripped:
            pieces.append(stripped)
        pieces.append(self._describe_stop(event))
        return "\n".join(filter(None, pieces))

    def _handle_evaluate(self, expr: str) -> str:
        if not self._dap or not self._current_frame:
            return "[python] no active frame"
        try:
            response = self._dap.send_request(
                "evaluate",
                {
                    "expression": expr,
                    "frameId": self._current_frame,
                    "context": "repl",
                },
            )
        except Exception as exc:
            return f"[python] eval error: {exc}"
        body = response.get("body", {})
        result = body.get("result", "")
        typ = body.get("type")
        if typ:
            return f"{expr} = {result} ({typ})"
        return f"{expr} = {result}"

    def _handle_locals(self) -> str:
        if not self._dap or not self._current_frame:
            return "[python] no active frame"
        try:
            scopes = self._dap.send_request("scopes", {"frameId": self._current_frame})
        except Exception as exc:
            return f"[python] scopes error: {exc}"
        scope_list = scopes.get("body", {}).get("scopes", [])
        locals_ref = None
        for scope in scope_list:
            if scope.get("name", "").lower() in {"locals", "local"}:
                locals_ref = scope.get("variablesReference")
                break
        if not locals_ref:
            return "[python] no locals scope"
        try:
            vars_resp = self._dap.send_request("variables", {"variablesReference": locals_ref})
        except Exception as exc:
            return f"[python] variables error: {exc}"
        variables = vars_resp.get("body", {}).get("variables", [])
        if not variables:
            return "[python] no locals"
        lines = ["Locals:"]
        for var in variables:
            name = var.get("name", "<unknown>")
            value = var.get("value", "")
            vtype = var.get("type")
            if vtype:
                lines.append(f"  {name} = {value} ({vtype})")
            else:
                lines.append(f"  {name} = {value}")
        return "\n".join(lines)

    def _render_stack(self) -> str:
        if not self._dap or not self._current_thread:
            return "[python] no stack available"
        try:
            response = self._dap.send_request(
                "stackTrace",
                {
                    "threadId": self._current_thread,
                    "startFrame": 0,
                    "levels": 40,
                },
            )
        except Exception as exc:
            return f"[python] stack error: {exc}"
        frames = response.get("body", {}).get("stackFrames", [])
        if not frames:
            return "[python] empty stack"
        lines: list[str] = []
        for idx, frame in enumerate(frames):
            name = frame.get("name", "<frame>")
            source = frame.get("source", {})
            file_path = source.get("path") or source.get("name") or "<unknown>"
            line = frame.get("line")
            lines.append(f"#{idx} {file_path}:{line} in {name}")
        top = frames[0]
        self._current_frame = top.get("id")
        return "\n".join(lines)

    def _describe_stop(self, event: Optional[Dict[str, Any]]) -> str:
        if not event:
            return "[python] program running..."
        reason = event.get("body", {}).get("reason", "stopped")
        description = event.get("body", {}).get("description")
        text_bits = [f"[python] stopped: {reason}"]
        if description:
            text_bits.append(description)
        thread_id = event.get("body", {}).get("threadId")
        if isinstance(thread_id, int):
            self._current_thread = thread_id
        stack = self._render_stack()
        if stack:
            text_bits.append(stack)
        self._last_stop_reason = reason
        return "\n".join(filter(None, text_bits))

    def _record_exit(self, event: Dict[str, Any]) -> None:
        body = event.get("body", {})
        exit_code = body.get("exitCode") or body.get("exitcode")
        if isinstance(exit_code, int):
            self._last_exit_code = exit_code
        self._current_thread = None
        self._current_frame = None

    def _format_exit_message(self) -> str:
        if self._last_exit_code is None:
            return "[python] program exited"
        return f"[python] program exited with code {self._last_exit_code}"

    def _pick_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self._listen_host, 0))
            return s.getsockname()[1]

    def _connect_debugpy(self, port: int) -> _DAPClient:
        deadline = time.monotonic() + 5.0
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                return _DAPClient(self._listen_host, port)
            except Exception as exc:  # pragma: no cover - depends on timing
                last_error = exc
                time.sleep(0.1)
        raise RuntimeError(f"unable to connect to debugpy: {last_error}")
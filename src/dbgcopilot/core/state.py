"""Session state scaffolding (POC)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable, List, Any


@dataclass
class Attempt:
    cmd: str
    output_snippet: str = ""


@dataclass
class SessionState:
    session_id: str
    goal: str = ""
    facts: list[str] = field(default_factory=list)
    chatlog: list[str] = field(default_factory=list)  # alternating User:/Assistant: lines
    attempts: list[Attempt] = field(default_factory=list)
    last_output: str = ""
    config: dict[str, str] = field(default_factory=dict)
    provider_name: str = "openrouter"
    provider_api_key: Optional[str] = None
    model_override: Optional[str] = None
    colors_enabled: bool = True
    selected_provider: Optional[str] = None
    pending_command: Optional[str] = None
    auto_accept_commands: bool = False
    pending_outputs: List[str] = field(default_factory=list)
    debugger_output_sink: Optional[Callable[[str], None]] = None
    pending_chat: List[str] = field(default_factory=list)
    chat_output_sink: Optional[Callable[[str], None]] = None
    last_answer_streamed: bool = False
    pending_chat_events: list[dict[str, Any]] = field(default_factory=list)

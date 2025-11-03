"""Session state scaffolding (POC)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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

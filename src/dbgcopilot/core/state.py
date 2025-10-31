"""Session state scaffolding (POC)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Attempt:
    cmd: str
    output_snippet: str = ""


@dataclass
class SessionState:
    session_id: str
    goal: str = ""
    facts: List[str] = field(default_factory=list)
    chatlog: List[str] = field(default_factory=list)  # alternating User:/Assistant: lines
    attempts: List[Attempt] = field(default_factory=list)
    last_output: str = ""
    config: Dict[str, str] = field(default_factory=dict)
    provider_name: str = "openrouter"
    provider_api_key: Optional[str] = None
    model_override: Optional[str] = None
    colors_enabled: bool = True

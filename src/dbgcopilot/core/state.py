"""Session state scaffolding (POC)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Attempt:
    cmd: str
    output_snippet: str = ""


@dataclass
class SessionState:
    session_id: str
    goal: str = ""
    mode: str = "interactive"  # or "auto"
    facts: List[str] = field(default_factory=list)
    attempts: List[Attempt] = field(default_factory=list)
    last_output: str = ""
    config: Dict[str, str] = field(default_factory=dict)
    # selected LLM provider name
    selected_provider: str = "mock-local"

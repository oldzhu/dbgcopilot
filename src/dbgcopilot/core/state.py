"""Session state scaffolding (POC)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable, List, Any, Dict, Mapping


DEFAULT_AUTO_ROUND_LIMIT = 64


def resolve_auto_round_limit(config: Mapping[str, str] | None) -> int:
    """Return the configured auto-approve round limit or the default."""
    if config:
        for key in ("auto_round_limit", "auto_rounds_limit"):
            raw = config.get(key)
            if raw is None:
                continue
            try:
                limit = int(raw)
            except (TypeError, ValueError):
                continue
            if limit > 0:
                return limit
    return DEFAULT_AUTO_ROUND_LIMIT

@dataclass
class Attempt:
    cmd: str
    output_snippet: str = ""


def _new_str_list() -> List[str]:
    return []


def _new_attempt_list() -> List[Attempt]:
    return []


def _new_config_dict() -> Dict[str, str]:
    return {}


def _new_chat_event_list() -> List[Dict[str, Any]]:
    return []


@dataclass
class SessionState:
    session_id: str
    goal: str = ""
    facts: List[str] = field(default_factory=_new_str_list)
    chatlog: List[str] = field(default_factory=_new_str_list)  # alternating User:/Assistant: lines
    attempts: List[Attempt] = field(default_factory=_new_attempt_list)
    last_output: str = ""
    config: Dict[str, str] = field(default_factory=_new_config_dict)
    provider_name: str = "openrouter"
    provider_api_key: Optional[str] = None
    model_override: Optional[str] = None
    colors_enabled: bool = True
    selected_provider: Optional[str] = None
    pending_command: Optional[str] = None
    auto_accept_commands: bool = False
    pending_outputs: List[str] = field(default_factory=_new_str_list)
    debugger_output_sink: Optional[Callable[[str], None]] = None
    pending_chat: List[str] = field(default_factory=_new_str_list)
    chat_output_sink: Optional[Callable[[str], None]] = None
    last_answer_streamed: bool = False
    pending_chat_events: List[Dict[str, Any]] = field(default_factory=_new_chat_event_list)
    auto_rounds_remaining: Optional[int] = None
    auto_loop_depth: int = 0
    chat_event_sink: Optional[Callable[[Dict[str, Any]], None]] = None

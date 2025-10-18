"""LLM provider registry and simple providers (POC).

This module exposes a registry of providers and a small mock provider for local testing.
Providers must implement `ask(prompt: str) -> str`.
"""
from __future__ import annotations

from typing import Callable, Dict


class Provider:
    def __init__(self, name: str, ask_fn: Callable[[str], str], meta: Dict[str, str] | None = None):
        self.name = name
        self.ask = ask_fn
        self.meta = meta or {}


_REGISTRY: Dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    _REGISTRY[provider.name] = provider


def list_providers() -> list[str]:
    return list(_REGISTRY.keys())


def get_provider(name: str) -> Provider | None:
    return _REGISTRY.get(name)


# A very small deterministic mock provider for testing
def _mock_ask(prompt: str) -> str:
    # Very naive deterministic reply
    if "explain" in prompt.lower():
        return "(mock) This output shows a crash in main; inspect backtrace (bt)."
    if "convert" in prompt.lower() or "pseudo" in prompt.lower():
        return "(mock) Pseudocode: function foo() { /* ... */ }"
    return "(mock) I suggest running 'bt' and 'info locals'."


register_provider(Provider("mock-local", _mock_ask, {"desc": "Local deterministic mock provider"}))

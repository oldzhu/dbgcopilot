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

try:
    # Lazy import of openrouter integration to avoid hard dependency for tests
    from . import openrouter

    # Cache a provider function bound to default env/session config; the orchestrator can supply per-session later
    _openrouter_default = openrouter.create_provider()

    def _openrouter_ask(prompt: str) -> str:
        return _openrouter_default(prompt)

    register_provider(Provider("openrouter", _openrouter_ask, {"desc": "OpenRouter API provider (requires OPENROUTER_API_KEY)"}))
except Exception:
    # If import fails (requests not installed), we simply don't register OpenRouter at import time
    pass

try:
    # Generic OpenAI-compatible HTTP provider (configurable via env/session)
    from . import openai_compat as _oa

    def _oa_http_default(prompt: str) -> str:
        # Uses env-only defaults; orchestrator may wrap with session-specific provider later
        ask_fn = _oa.create_provider(session_config=None, name="openai-http")
        return ask_fn(prompt)

    register_provider(Provider("openai-http", _oa_http_default, {"desc": "Generic OpenAI-compatible endpoint (configure base URL/API key/model)"}))

    def _ollama_default(prompt: str) -> str:
        ask_fn = _oa.create_provider(session_config=None, name="ollama")
        return ask_fn(prompt)

    register_provider(Provider("ollama", _ollama_default, {"desc": "Local Ollama via OpenAI-compatible /v1/chat/completions"}))
except Exception:
    pass

# Convenience aliases for common OpenAI-compatible vendors
try:
    from . import openai_compat as _oa2

    def _mk_provider(name: str):
        def ask(prompt: str) -> str:
            ask_fn = _oa2.create_provider(session_config=None, name=name)
            return ask_fn(prompt)
        return ask

    register_provider(Provider("deepseek", _mk_provider("deepseek"), {"desc": "DeepSeek OpenAI-compatible API"}))
    register_provider(Provider("qwen", _mk_provider("qwen"), {"desc": "Qwen via DashScope OpenAI-compatible API"}))
    register_provider(Provider("kimi", _mk_provider("kimi"), {"desc": "Kimi (Moonshot) OpenAI-compatible API"}))
    register_provider(Provider("glm", _mk_provider("glm"), {"desc": "Zhipu GLM OpenAI-compatible API"}))
    register_provider(Provider("llama-cpp", _mk_provider("llama-cpp"), {"desc": "llama.cpp local server (OpenAI-compatible)"}))
except Exception:
    pass


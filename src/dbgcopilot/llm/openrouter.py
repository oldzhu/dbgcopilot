"""OpenRouter provider integration (POC).

This module implements a minimal client to OpenRouter's API for text generation.
It expects an API key in the environment variable OPENROUTER_API_KEY or a key
passed via provider.meta or session.config under 'openrouter_api_key'.

Note: This is a lightweight POC. For production usage, improve error handling,
timeouts, retries, and don't log secrets.
"""
from __future__ import annotations

import os
import json
from typing import Optional


def _get_api_key(meta: dict | None = None, session_config: dict | None = None) -> Optional[str]:
    # Priority: meta -> session_config -> env
    if meta and "api_key" in meta:
        return meta["api_key"]
    if session_config and "openrouter_api_key" in session_config:
        return session_config["openrouter_api_key"]
    return os.environ.get("OPENROUTER_API_KEY")


def _ask_openrouter(prompt: str, meta: dict | None = None, session_config: dict | None = None) -> str:
    # Lazy import to avoid adding hard runtime deps for tests
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests library is required for OpenRouter provider") from e

    key = _get_api_key(meta, session_config)
    if not key:
        raise RuntimeError("OpenRouter API key not configured (OPENROUTER_API_KEY or session config)")

    # Basic OpenRouter text generation endpoint (model-agnostic POC)
    url = "https://openrouter.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Minimal body: user prompt as system/user messages depending on model
    body = {
        "model": "gpt-4o-mini",  # default POC; users can override via meta
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.2,
    }

    # Allow overriding model from meta
    if meta and "model" in meta:
        body["model"] = meta["model"]

    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # Expecting standard OpenAI-like shape: choices[0].message.content
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        # fallback to raw JSON
        return json.dumps(data)


def create_provider(session_config: dict | None = None):
    # Returns a callable that accepts prompt and returns string
    def ask(prompt: str) -> str:
        return _ask_openrouter(prompt, meta=None, session_config=session_config)

    return ask

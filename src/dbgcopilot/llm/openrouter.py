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

    # OpenRouter chat completions endpoint (OpenAI-compatible)
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Optional but recommended headers for OpenRouter identification (non-sensitive)
        "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/oldzhu/dbgcopilot"),
        "X-Title": os.environ.get("OPENROUTER_TITLE", "dbgcopilot"),
    }
    # Minimal body: user prompt as system/user messages depending on model
    # Determine model preference: meta -> session_config -> env -> default
    model = (
        (meta or {}).get("model")
        or (session_config or {}).get("openrouter_model")
        or os.environ.get("OPENROUTER_MODEL")
        or "openai/gpt-4o-mini"
    )

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20)
    except Exception as e:  # requests.RequestException in most cases
        raise RuntimeError(f"OpenRouter request failed: {e}") from e

    # If non-2xx, surface body text to aid debugging
    if not (200 <= resp.status_code < 300):
        text = (resp.text or "").strip()
        snippet = text[:200].replace("\n", " ")
        raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {snippet}")

    # Parse JSON response; if not JSON, show the raw response body for diagnosis
    try:
        data = resp.json()
    except Exception as e:
        raw = resp.text or ""
        # Prefer showing full provider response to help troubleshooting
        raise RuntimeError(f"OpenRouter returned non-JSON response:\n{raw}") from e
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


def list_models(session_config: dict | None = None) -> list[str]:
    """Return a list of available model IDs from OpenRouter.

    Tries the public models endpoint; if an API key is available, it will be sent.
    """
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests library is required to list OpenRouter models") from e

    key = _get_api_key(None, session_config)
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Accept": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        raise RuntimeError(f"OpenRouter models request failed: {e}") from e

    if not (200 <= resp.status_code < 300):
        text = (resp.text or "").strip()
        snippet = text[:200].replace("\n", " ")
        raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {snippet}")

    try:
        data = resp.json()
    except Exception as e:
        snippet = (resp.text or "")[:200].replace("\n", " ")
        raise RuntimeError(f"OpenRouter returned non-JSON response: {snippet}") from e

    models = []
    try:
        for m in data.get("data", []) or []:
            mid = m.get("id") or m.get("name")
            if isinstance(mid, str):
                models.append(mid)
    except Exception:
        pass
    return models

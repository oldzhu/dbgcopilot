"""OpenAI-compatible provider integration (configurable).

This module implements a minimal HTTP client for any endpoint that follows the
OpenAI Chat Completions API shape (POST /v1/chat/completions).

Configuration precedence (per provider name, e.g., 'openai-http' or 'ollama'):
- Session config keys (highest):
  - {name}_base_url (e.g., openai_http_base_url / ollama_base_url)
  - {name}_api_key
  - {name}_model
  - {name}_headers (dict or JSON string)
  - {name}_path (defaults to /v1/chat/completions)
- Environment variables (next): uppercased prefix derived from name by non-alnum->'_' mapping
  - {PREFIX}_BASE_URL, {PREFIX}_API_KEY, {PREFIX}_MODEL, {PREFIX}_HEADERS (JSON), {PREFIX}_PATH
- Built-in defaults (lowest):
  - For name == 'ollama': base_url=http://localhost:11434, model='llama3.1', no API key
  - Otherwise: require base_url and API key

Note: This is a lightweight POC client. For production, add retries, timeouts, and robust error handling.
"""
from __future__ import annotations

import os
import json
import re
from typing import Optional, Dict, Any, Tuple


def _slug_to_env_prefix(name: str) -> str:
    # Convert provider name into ENV prefix: 'openai-http' -> 'OPENAI_HTTP'
    return re.sub(r"[^A-Za-z0-9]+", "_", name).upper()


def _get_cfg(name: str, session_config: Optional[dict]) -> Dict[str, Any]:
    sc = session_config or {}
    key = name.replace("-", "_")  # session keys use underscores
    prefix = _slug_to_env_prefix(name)

    def pick(sc_key: str, env_key: str, default: Optional[str] = None) -> Optional[str]:
        if sc_key in sc and sc.get(sc_key):
            return sc.get(sc_key)
        if env_key in os.environ and os.environ.get(env_key):
            return os.environ.get(env_key)
        return default

    base_url = pick(f"{key}_base_url", f"{prefix}_BASE_URL", None)
    api_key = pick(f"{key}_api_key", f"{prefix}_API_KEY", None)
    model = pick(f"{key}_model", f"{prefix}_MODEL", None)
    path = pick(f"{key}_path", f"{prefix}_PATH", "/v1/chat/completions")
    headers_raw = pick(f"{key}_headers", f"{prefix}_HEADERS", None)

    headers: Dict[str, str] = {}
    if headers_raw:
        try:
            if isinstance(headers_raw, str):
                headers = json.loads(headers_raw)
            elif isinstance(headers_raw, dict):
                headers = dict(headers_raw)
        except Exception:
            # ignore malformed headers
            headers = {}

    # Apply built-in defaults for known names
    if name == "ollama":
        base_url = base_url or "http://localhost:11434"
        model = model or "llama3.1"
        # No API key required by default for local Ollama
    elif name == "deepseek":
        base_url = base_url or "https://api.deepseek.com"
        model = model or "deepseek-chat"
    elif name == "qwen":
        # DashScope OpenAI-compatible endpoint
        base_url = base_url or "https://dashscope.aliyuncs.com"
        if path == "/v1/chat/completions":
            path = "/compatible-mode/v1/chat/completions"
        model = model or "qwen-turbo"
    elif name == "kimi":
        base_url = base_url or "https://api.moonshot.cn"
        model = model or "moonshot-v1-8k"
    elif name == "glm":
        base_url = base_url or "https://open.bigmodel.cn/api/paas/v4"
        if not path or path == "/v1/chat/completions":
            path = "/chat/completions"
        model = model or "glm-4"
    elif name == "llama-cpp":
        # llama.cpp built-in server (OpenAI API compatible via --api), default port 8080
        base_url = base_url or "http://localhost:8080"
        # Most llama.cpp servers accept arbitrary model ids; default to a generic label
        model = model or "llama"
    elif name == "modelscope":
        # ModelScope OpenAI-compatible inference endpoint
        base_url = base_url or "https://api-inference.modelscope.cn"
        model = model or "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "path": path or "/v1/chat/completions",
        "headers": headers,
    }


def _extract_usage(data: Dict[str, Any], provider_name: str, model: str) -> Dict[str, Any]:
    usage: Dict[str, Any] = {
        "provider": provider_name,
        "model": model,
    }
    usage_obj = data.get("usage") if isinstance(data.get("usage"), dict) else {}

    def _as_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    def _as_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return None

    if isinstance(usage_obj, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = _as_int(usage_obj.get(key))
            if val is not None:
                usage[key] = val
        for cost_key in ("total_cost", "total_cost_usd", "cost"):
            val = _as_float(usage_obj.get(cost_key))
            if val is not None:
                usage["cost"] = val
                break

    return usage


def _ask_openai_compat(
    prompt: str,
    name: str,
    session_config: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests library is required for OpenAI-compatible providers") from e

    cfg = _get_cfg(name, session_config)
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key")
    model = cfg.get("model") or "gpt-4o-mini"
    path = cfg.get("path") or "/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(cfg.get("headers") or {})
    # Attach bearer token if provided and caller didn't override Authorization
    if api_key and not any(h.lower() == "authorization" for h in headers.keys()):
        headers["Authorization"] = f"Bearer {api_key}"

    if not base_url:
        raise RuntimeError(f"{name}: base_url not configured. Set {name.replace('-', '_')}_base_url in session config or { _slug_to_env_prefix(name) }_BASE_URL in env.")

    url = f"{base_url}{path if path.startswith('/') else '/' + path}"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20)
    except Exception as e:
        raise RuntimeError(f"{name} request failed: {e}") from e

    if not (200 <= resp.status_code < 300):
        snippet = (resp.text or "")[:200].replace("\n", " ")
        raise RuntimeError(f"{name} HTTP {resp.status_code}: {snippet}")

    content_type = resp.headers.get("Content-Type", "").lower()
    if "json" not in content_type:
        snippet = (resp.text or "")[:400].replace("\n", " ")
        raise RuntimeError(
            f"{name} returned non-JSON payload (content-type={content_type or 'unknown'}). "
            f"Response snippet: {snippet}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raw = (resp.text or "")[:400]
        raise RuntimeError(f"{name} returned invalid JSON (status {resp.status_code}). Snippet: {raw}") from e

    # Try OpenAI-like shape first
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        # fall back to raw json text
        content = json.dumps(data)

    usage = _extract_usage(data, name, model)
    return content, usage


def create_provider(session_config: dict | None = None, name: str = "openai-http"):
    """Return an ask(prompt) function bound to session_config and provider name.

    Examples:
    - name='openai-http': use {openai_http_*} keys or OPENAI_HTTP_* env vars
    - name='ollama': use {ollama_*} keys or OLLAMA_* env vars (defaults base_url and model)
    """
    def ask(prompt: str) -> str:
        content, usage = _ask_openai_compat(prompt, name=name, session_config=session_config)
        setattr(ask, "last_usage", usage)
        return content

    setattr(ask, "last_usage", {})
    return ask


def list_models(session_config: dict | None = None, name: str = "openai-http") -> list[str]:
    """Attempt to list models for an OpenAI-compatible provider.

    Strategy:
    - Try standard OpenAI endpoint: GET <base_url>/v1/models (bearer if available)
    - Special-case ollama: if /v1/models fails, try GET <base_url>/api/tags
    - On error, return [] and allow REPLs to show a helpful message
    """
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests library is required to list models for OpenAI-compatible providers") from e

    cfg = _get_cfg(name, session_config)
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if not base_url:
        raise RuntimeError(f"{name}: base_url not configured; cannot list models")

    # 1) Try OpenAI-compatible /v1/models
    try:
        url = f"{base_url}/v1/models"
        resp = requests.get(url, headers=headers, timeout=15)
        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
                models: list[str] = []
                for m in (data.get("data") or []):
                    mid = m.get("id") or m.get("name")
                    if isinstance(mid, str):
                        models.append(mid)
                if models:
                    return models
            except Exception:
                pass
    except Exception:
        pass

    # 2) Special-case Ollama fallback: /api/tags
    if name == "ollama":
        try:
            url = f"{base_url}/api/tags"
            resp = requests.get(url, headers=headers, timeout=15)
            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json() or {}
                    models_list = []
                    for m in (data.get("models") or []):
                        mid = m.get("name") or m.get("model")
                        if isinstance(mid, str):
                            models_list.append(mid)
                    return models_list
                except Exception:
                    return []
        except Exception:
            return []

    return []

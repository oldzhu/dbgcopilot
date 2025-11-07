"""Utilities for handling provider parameter overrides."""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

SESSION_SUFFIX = "_params"
CLEAR_SENTINEL = object()

_COMMON_ALIASES: Dict[str, str] = {
    "temperature": "temperature",
    "temp": "temperature",
    "max_tokens": "max_tokens",
    "top_p": "top_p",
    "top_k": "top_k",
    "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "stop": "stop",
    "stop_sequences": "stop",
    "repeat_penalty": "extras.repeat_penalty",
    "mirostat": "extras.mirostat",
    "web_search": "extras.enable_web_search",
}

_INT_BASE_NAMES = {"max_tokens", "top_k", "mirostat"}
_FLOAT_BASE_NAMES = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "repeat_penalty"}
_LIST_BASE_NAMES = {"stop"}

_BOOL_TRUE = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}


def params_key(provider_name: str) -> str:
    return provider_name.replace("-", "_") + SESSION_SUFFIX


def _alias_map(meta: Dict[str, Any] | None) -> Dict[str, str]:
    mapping = {k.lower(): v for k, v in _COMMON_ALIASES.items()}
    if not meta:
        return mapping
    aliases = meta.get("param_aliases")
    if isinstance(aliases, dict):
        for key, value in aliases.items():
            mapping[str(key).lower()] = str(value)
    return mapping


def _reverse_alias_map(meta: Dict[str, Any] | None) -> Dict[str, str]:
    rev: Dict[str, str] = {}
    amap = _alias_map(meta)
    for alias, canonical in amap.items():
        rev.setdefault(canonical, alias)
    return rev


def canonicalize_param(meta: Dict[str, Any] | None, param: str) -> Tuple[str, str]:
    name = str(param).strip()
    if not name:
        raise ValueError("Parameter name is required")
    amap = _alias_map(meta)
    canonical = amap.get(name.lower(), name)
    return canonical, name


def display_name(meta: Dict[str, Any] | None, canonical: str) -> str:
    rev = _reverse_alias_map(meta)
    return rev.get(canonical, canonical)


def list_capabilities(meta: Dict[str, Any] | None) -> list[str]:
    caps = [] if meta is None else meta.get("capabilities")
    if isinstance(caps, list):
        return [str(c) for c in caps]
    return []


def get_session_params(config: Dict[str, Any], provider: str) -> Dict[str, Any]:
    store = config.get(params_key(provider))
    if isinstance(store, dict):
        return dict(store)
    return {}


def set_session_param(config: Dict[str, Any], provider: str, canonical: str, value: Any) -> None:
    key = params_key(provider)
    store = config.get(key)
    if not isinstance(store, dict):
        store = {}
        config[key] = store
    store[canonical] = value


def clear_session_param(config: Dict[str, Any], provider: str, canonical: str) -> bool:
    key = params_key(provider)
    store = config.get(key)
    if not isinstance(store, dict):
        return False
    removed = canonical in store
    store.pop(canonical, None)
    if not store:
        config.pop(key, None)
    return removed


def clear_all_session_params(config: Dict[str, Any], provider: str) -> bool:
    key = params_key(provider)
    return config.pop(key, None) is not None


def parse_value(meta: Dict[str, Any] | None, param: str, raw_value: Any) -> Tuple[str, Any, bool]:
    canonical, _ = canonicalize_param(meta, param)
    value, cleared = _coerce_value(canonical, raw_value)
    return canonical, value, cleared


def _coerce_value(canonical: str, raw_value: Any) -> Tuple[Any, bool]:
    if isinstance(raw_value, (dict, list, bool)):
        return raw_value, False
    if raw_value is None:
        return None, True
    if isinstance(raw_value, (int, float)):
        return raw_value, False
    text = str(raw_value).strip()
    if not text:
        return None, True
    lowered = text.lower()
    if lowered in {"none", "null", "clear"}:
        return None, True
    if lowered in _BOOL_TRUE:
        return True, False
    if lowered in _BOOL_FALSE:
        return False, False

    base = canonical.split(".")[-1]
    if base in _INT_BASE_NAMES:
        try:
            return int(float(text)), False
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Expected integer value for {canonical}") from exc
    if base in _FLOAT_BASE_NAMES:
        try:
            return float(text), False
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Expected numeric value for {canonical}") from exc
    if base in _LIST_BASE_NAMES:
        if text.startswith("["):
            try:
                value = json.loads(text)
                if isinstance(value, list):
                    return [str(v) for v in value], False
            except Exception as exc:  # pragma: no cover
                raise ValueError(f"Invalid list value for {canonical}") from exc
        parts = [segment.strip() for segment in text.split(",") if segment.strip()]
        return parts or [text], False

    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text), False
        except Exception:
            pass
    return text, False


def apply_params(
    body: Dict[str, Any],
    params: Dict[str, Any],
    meta: Dict[str, Any] | None = None,
    *,
    assume_canonical: bool = False,
) -> Dict[str, Any]:
    if not params:
        return body
    for key, value in params.items():
        canonical = key if assume_canonical else canonicalize_param(meta, key)[0]
        _apply_path(body, canonical, value)
    return body


def _apply_path(target: Dict[str, Any], canonical: str, value: Any) -> None:
    parts = [segment for segment in canonical.split(".") if segment]
    if not parts:
        return
    current = target
    for segment in parts[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    leaf = parts[-1]
    if value is None:
        if isinstance(current, dict):
            current.pop(leaf, None)
        return
    if leaf == "stop" and isinstance(value, str):
        value = [value]
    current[leaf] = value


def serialize_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def list_session_params(config: Dict[str, Any], provider: str) -> Dict[str, Any]:
    return get_session_params(config, provider)


__all__ = [
    "CLEAR_SENTINEL",
    "apply_params",
    "canonicalize_param",
    "clear_all_session_params",
    "clear_session_param",
    "display_name",
    "list_capabilities",
    "list_session_params",
    "params_key",
    "parse_value",
    "serialize_value",
    "set_session_param",
    "get_session_params",
]

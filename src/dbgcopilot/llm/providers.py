# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false

"""LLM provider registry backed by a configurable JSON file."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional, cast
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from . import openai_compat, openrouter

CONFIG_ENV_VAR = "DBGCOPILOT_LLM_PROVIDERS"
CONFIG_FILENAME = "llm_providers.json"
DEFAULT_CONFIG: Dict[str, Any] = {
    "providers": {
        "mock-local": {
            "kind": "mock",
            "description": "Local deterministic mock provider",
            "capabilities": [],
        },
        "openrouter": {
            "kind": "openrouter",
            "description": "OpenRouter API provider (requires OPENROUTER_API_KEY)",
            "default_model": "openai/gpt-4o-mini",
            "supports_model_list": True,
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "stop_sequences",
                "thinking",
            ],
            "param_aliases": {
                "enable_thinking": "thinking.enabled",
                "thinking_budget_tokens": "thinking.max_tokens",
            },
        },
        "openai-http": {
            "kind": "openai-compatible",
            "description": "Generic OpenAI-compatible endpoint (configure base URL/API key/model)",
            "base_url": "",
            "path": "/v1/chat/completions",
            "default_model": "gpt-4o-mini",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "stop_sequences",
            ],
        },
        "ollama": {
            "kind": "openai-compatible",
            "description": "Local Ollama via OpenAI-compatible /v1/chat/completions",
            "base_url": "http://localhost:11434",
            "path": "/v1/chat/completions",
            "default_model": "llama3.1",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "top_k",
                "stop_sequences",
            ],
            "param_aliases": {
                "mirostat": "extras.mirostat",
            },
        },
        "deepseek": {
            "kind": "openai-compatible",
            "description": "DeepSeek OpenAI-compatible API",
            "base_url": "https://api.deepseek.com",
            "path": "/v1/chat/completions",
            "default_model": "deepseek-chat",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
                "thinking",
            ],
            "param_aliases": {
                "enable_thinking": "thinking.enabled",
            },
        },
        "qwen": {
            "kind": "openai-compatible",
            "description": "Qwen via DashScope OpenAI-compatible API",
            "base_url": "https://dashscope.aliyuncs.com",
            "path": "/compatible-mode/v1/chat/completions",
            "default_model": "qwen-turbo",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
            ],
        },
        "kimi": {
            "kind": "openai-compatible",
            "description": "Kimi (Moonshot) OpenAI-compatible API",
            "base_url": "https://api.moonshot.cn",
            "path": "/v1/chat/completions",
            "default_model": "kimi-k2-0905-preview",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
                "web_search",
            ],
            "param_aliases": {
                "web_search": "extras.enable_web_search",
            },
        },
        "zhipuglm": {
            "kind": "openai-compatible",
            "description": "Zhipu GLM OpenAI-compatible API",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "path": "/chat/completions",
            "default_model": "glm-4",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
                "web_search",
            ],
            "param_aliases": {
                "web_search": "extras.enable_web_search",
            },
        },
        "gemini": {
            "kind": "openai-compatible",
            "description": "Google Gemini OpenAI-compatible API",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "path": "/chat/completions",
            "default_model": "gemini-2.5-flash",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
            ],
        },
        "llama-cpp": {
            "kind": "openai-compatible",
            "description": "llama.cpp local server (OpenAI-compatible)",
            "base_url": "http://localhost:8080",
            "path": "/v1/chat/completions",
            "default_model": "llama",
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "top_k",
                "stop_sequences",
                "repeat_penalty",
                "mirostat",
            ],
            "param_aliases": {
                "repeat_penalty": "extras.repeat_penalty",
                "mirostat": "extras.mirostat",
            },
        },
        "modelscope": {
            "kind": "openai-compatible",
            "description": "ModelScope OpenAI-compatible inference API",
            "base_url": "https://api-inference.modelscope.cn",
            "path": "/v1/chat/completions",
            "default_model": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
            "supports_model_list": True,
            "capabilities": [
                "temperature",
                "max_tokens",
                "top_p",
                "stop_sequences",
                "thinking",
            ],
            "param_aliases": {
                "thinking_budget_tokens": "thinking.max_tokens",
            },
        },
    }
}


class Provider:
    """Container for provider metadata and factory helpers."""

    def __init__(
        self,
        name: str,
        kind: str,
        meta: Dict[str, Any],
        factory: Callable[[Optional[dict[str, Any]], Dict[str, Any]], Callable[[str], str]],
    ) -> None:
        self.name = name
        self.kind = kind
        copied = dict(meta or {})
        copied.setdefault("kind", kind)
        desc = copied.get("description") or copied.get("desc") or ""
        copied.setdefault("description", desc)
        copied.setdefault("desc", desc)
        copied.setdefault("name", name)
        self.meta = copied
        self._factory = factory
        # Default ask function without per-session overrides (backwards compatible)
        self.ask = self.create_client(None)

    def create_client(self, session_config: Optional[dict[str, Any]] = None) -> Callable[[str], str]:
        return self._factory(session_config, self.meta)


_config_cache: Optional[Dict[str, Any]] = None
_registry: Dict[str, Provider] = {}


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "configs").exists():
            return parent
    return Path.cwd().resolve()


def _config_path() -> Path:
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path
    return _repo_root() / "configs" / CONFIG_FILENAME


def config_path() -> Path:
    """Return the resolved provider config path."""
    return _config_path()


def _ensure_config_file() -> None:
    path = _config_path()
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_config(refresh: bool = False) -> Dict[str, Any]:
    global _config_cache
    if refresh or _config_cache is None:
        _ensure_config_file()
        path = _config_path()
        try:
            raw = path.read_text(encoding="utf-8")
            loaded: Any = json.loads(raw or "{}")
        except Exception:
            loaded = {}
        data_dict: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
        providers = data_dict.get("providers")
        if not isinstance(providers, dict):
            providers = {}
            data_dict["providers"] = providers
        else:
            providers = data_dict["providers"]
        if _merge_default_providers(providers):
            _save_config(data_dict)
            data_dict = _config_cache
        else:
            _config_cache = data_dict
    return _config_cache


def _save_config(data: Dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    global _config_cache
    _config_cache = dict(data)


def _mock_ask(prompt: str) -> str:
    lowered = prompt.lower()
    if "explain" in lowered:
        return "(mock) This output shows a crash in main; inspect backtrace (bt)."
    if "convert" in lowered or "pseudo" in lowered:
        return "(mock) Pseudocode: function foo() { /* ... */ }"
    return "(mock) I suggest running 'bt' and 'info locals'."


def _provider_defaults(meta: Dict[str, Any]) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for key in ("base_url", "path", "default_model", "headers", "model"):
        if key in meta and meta.get(key) not in {None, ""}:
            defaults[key] = meta.get(key)
    return defaults


def _merge_default_providers(providers: Dict[str, Any]) -> bool:
    defaults = DEFAULT_CONFIG.get("providers") or {}
    merged = False
    for name, entry in defaults.items():
        if name not in providers:
            providers[name] = dict(entry)
            merged = True
    return merged


def _build_provider(name: str, entry: Dict[str, Any]) -> Optional[Provider]:
    kind = str(entry.get("kind", "openai-compatible")).lower()
    meta = dict(entry)
    meta.setdefault("name", name)
    meta.setdefault("kind", kind)

    if kind == "mock":
        def _factory_mock(_session_config: Optional[dict[str, Any]], _meta: Dict[str, Any]) -> Callable[[str], str]:
            return _mock_ask

        return Provider(name, kind, meta, _factory_mock)

    if kind == "openrouter":
        def _factory_openrouter(session_config: Optional[dict[str, Any]], meta_ref: Dict[str, Any]) -> Callable[[str], str]:
            return openrouter.create_provider(session_config=session_config, meta=meta_ref)

        return Provider(name, kind, meta, _factory_openrouter)

    def _factory_openai(session_config: Optional[dict[str, Any]], meta_ref: Dict[str, Any]) -> Callable[[str], str]:
        defaults = _provider_defaults(meta_ref)
        return openai_compat.create_provider(
            session_config=session_config,
            name=name,
            defaults=defaults,
            meta=meta_ref,
        )

    return Provider(name, kind, meta, _factory_openai)


def _rebuild_registry() -> None:
    data = _load_config(refresh=True)
    providers = data.get("providers", {})
    registry: Dict[str, Provider] = {}
    for name in sorted(providers.keys()):
        provider = _build_provider(name, providers[name])
        if provider is None:
            continue
        registry[name] = provider
    global _registry
    _registry = registry


def _ensure_registry() -> None:
    if not _registry:
        _rebuild_registry()


def reload() -> None:
    """Reload provider registry from disk."""
    _rebuild_registry()


def list_providers() -> list[str]:
    _ensure_registry()
    return sorted(_registry.keys())


def get_provider(name: str) -> Optional[Provider]:
    _ensure_registry()
    return _registry.get(name)


def create_client(name: str, session_config: Optional[dict[str, Any]] = None) -> Callable[[str], str]:
    provider = get_provider(name)
    if provider is None:
        raise ValueError(f"Unknown provider: {name}")
    return provider.create_client(session_config)


def list_models(name: str, session_config: Optional[dict[str, Any]] = None) -> list[str]:
    provider = get_provider(name)
    if provider is None:
        raise ValueError(f"Unknown provider: {name}")
    if provider.kind == "openrouter":
        return openrouter.list_models(session_config=session_config)
    if provider.kind == "openai-compatible":
        defaults = _provider_defaults(provider.meta)
        return openai_compat.list_models(session_config=session_config, name=name, defaults=defaults)
    return []


def provider_config(name: str) -> Dict[str, Any]:
    data = _load_config(refresh=True)
    providers = data.get("providers", {})
    entry = providers.get(name)
    if entry is None:
        raise ValueError(f"Unknown provider: {name}")
    return dict(entry)


_FIELD_ALIAS = {
    "baseurl": "base_url",
    "base_url": "base_url",
    "path": "path",
    "model": "default_model",
    "default_model": "default_model",
    "desc": "description",
    "description": "description",
}


def add_provider(
    name: str,
    base_url: str,
    path: Optional[str] = None,
    default_model: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    if not name:
        raise ValueError("Provider name is required")
    data = _load_config(refresh=True)
    providers = data.setdefault("providers", {})
    if name in providers:
        raise ValueError(f"Provider '{name}' already exists")
    entry = {
        "kind": "openai-compatible",
        "description": description,
        "base_url": base_url,
        "path": path or "/v1/chat/completions",
        "default_model": default_model or "",
    }
    providers[name] = entry
    _save_config(data)
    _rebuild_registry()
    return dict(entry)


def set_provider_field(name: str, field: str, value: str) -> str:
    key = _FIELD_ALIAS.get(field.lower())
    if key is None:
        raise ValueError("Field must be one of: baseurl, path, model, desc")
    data = _load_config(refresh=True)
    providers = data.setdefault("providers", {})
    entry = providers.get(name)
    if entry is None:
        raise ValueError(f"Unknown provider: {name}")
    entry[key] = value
    _save_config(data)
    _rebuild_registry()
    return str(value)


def get_provider_field(name: str, field: Optional[str] = None) -> Any:
    entry = provider_config(name)
    if field is None:
        return entry
    key = _FIELD_ALIAS.get(field.lower())
    if key is None:
        raise ValueError("Field must be one of: baseurl, path, model, desc")
    return entry.get(key)


__all__ = [
    "Provider",
    "add_provider",
    "config_path",
    "create_client",
    "get_provider",
    "get_provider_field",
    "list_models",
    "list_providers",
    "provider_config",
    "reload",
    "set_provider_field",
]

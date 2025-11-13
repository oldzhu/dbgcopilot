"""REST endpoints for dbgweb."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from dbgcopilot.llm import providers as provider_registry

from ..services.session_manager import session_manager

router = APIRouter(prefix="/api")


@router.get("/status")
async def api_status() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/providers")
async def list_providers() -> JSONResponse:
    items: List[Dict[str, Any]] = []
    for name in sorted(provider_registry.list_providers()):
        info = provider_registry.get_provider(name)
        meta = info.meta if info else {}
        default_model = ""
        supports_model_list = False
        kind = ""
        if info:
            kind = getattr(info, "kind", "") or meta.get("kind", "")
            default_model = str(meta.get("default_model") or meta.get("model") or "")
            supports_model_list = bool(
                meta.get("supports_model_list")
                or (getattr(info, "kind", "") == "openrouter")
            )
        description = ""
        if meta:
            description = meta.get("description") or meta.get("desc") or ""
        items.append(
            {
                "id": name,
                "description": description,
                "default_model": default_model,
                "supports_model_list": supports_model_list,
                "kind": kind,
            }
        )
    return JSONResponse({"providers": items})


@router.get("/providers/{provider_id}/models")
async def list_provider_models(provider_id: str) -> JSONResponse:
    provider = provider_registry.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    try:
        models = provider_registry.list_models(provider_id)
    except Exception as exc:  # pragma: no cover - depends on external API availability
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"models": models})


@router.post("/sessions")
async def create_session(payload: Dict[str, Any]) -> JSONResponse:
    required = payload.get("debugger")
    provider = payload.get("provider")
    if not required or not provider:
        raise HTTPException(status_code=400, detail="debugger and provider are required")
    program = payload.get("program")
    classpath = payload.get("classpath")
    sourcepath = payload.get("sourcepath")
    main_class = payload.get("main_class")
    corefile = payload.get("corefile")
    model = payload.get("model")
    api_key = payload.get("api_key")
    auto_approve = bool(payload.get("auto_approve"))

    try:
        session, initial_messages = await session_manager.create_session(
            debugger=required,
            provider=provider,
            model=model,
            api_key=api_key,
            program=main_class or program,
            corefile=corefile,
            classpath=classpath,
            sourcepath=sourcepath,
            auto_approve=auto_approve,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"session_id": session.session_id, "initial_messages": initial_messages})


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> JSONResponse:
    try:
        session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    await session_manager.close_session(session_id)
    return JSONResponse({"status": "closed"})


@router.post("/sessions/{session_id}/command")
async def run_command(session_id: str, payload: Dict[str, Any]) -> JSONResponse:
    command = payload.get("command")
    if command is None:
        raise HTTPException(status_code=400, detail="command is required")
    try:
        session = session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    await session_manager.run_debugger_command(session, command)
    return JSONResponse({"status": "queued"})


@router.post("/sessions/{session_id}/chat")
async def run_chat(session_id: str, payload: Dict[str, Any]) -> JSONResponse:
    message = payload.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    try:
        session = session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")

    answer = await session_manager.run_chat(session, message)
    return JSONResponse({"status": "completed", "answer": answer})


@router.post("/sessions/{session_id}/auto-approve")
async def set_auto_approve(session_id: str, payload: Dict[str, Any]) -> JSONResponse:
    try:
        session = session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    enabled = bool(payload.get("enabled"))
    await session_manager.set_auto_approve(session, enabled)
    return JSONResponse({"status": "ok", "enabled": enabled})


@router.get("/workspace")
async def browse_workspace(path: Optional[str] = None) -> JSONResponse:
    base = Path.cwd().resolve()
    target = (base / (path or ".")).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path escapes workspace root")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    entries: List[Dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        entries.append(
            {
                "name": child.name,
                "is_dir": child.is_dir(),
                "path": str(child.relative_to(base)),
            }
        )
    return JSONResponse({"path": str(target.relative_to(base)), "entries": entries})

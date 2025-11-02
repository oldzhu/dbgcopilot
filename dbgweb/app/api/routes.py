"""REST endpoints for dbgweb."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from dbgcopilot.llm import providers as provider_registry

from ..services.session_manager import session_manager

router = APIRouter(prefix="/api")


@router.get("/status")
async def api_status() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/providers")
async def list_providers() -> JSONResponse:
    providers = []
    for name in sorted(provider_registry.list_providers()):
        info = provider_registry.get_provider(name)
        providers.append(
            {
                "id": name,
                "description": (info.meta.get("desc") if info and info.meta else ""),
            }
        )
    return JSONResponse({"providers": providers})


@router.post("/sessions")
async def create_session(payload: Dict[str, Any]) -> JSONResponse:
    required = payload.get("debugger")
    provider = payload.get("provider")
    if not required or not provider:
        raise HTTPException(status_code=400, detail="debugger and provider are required")
    program = payload.get("program")
    corefile = payload.get("corefile")
    model = payload.get("model")
    api_key = payload.get("api_key")

    session, initial_messages = await session_manager.create_session(
        debugger=required,
        provider=provider,
        model=model,
        api_key=api_key,
        program=program,
        corefile=corefile,
    )
    return JSONResponse({"session_id": session.session_id, "initial_messages": initial_messages})


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


@router.get("/workspace")
async def browse_workspace(path: Optional[str] = None) -> JSONResponse:
    base = Path.cwd().resolve()
    target = (base / (path or ".")).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path escapes workspace root")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        entries.append(
            {
                "name": child.name,
                "is_dir": child.is_dir(),
                "path": str(child.relative_to(base)),
            }
        )
    return JSONResponse({"path": str(target.relative_to(base)), "entries": entries})

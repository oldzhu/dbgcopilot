"""WebSocket endpoints for debugger and chat streaming."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.session_manager import session_manager

ws_router = APIRouter()


async def _consume_queue(queue: asyncio.Queue[str]) -> AsyncIterator[str]:
    while True:
        item = await queue.get()
        yield item
        queue.task_done()


@ws_router.websocket("/ws/debugger/{session_id}")
async def debugger_stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        session = session_manager.get_session(session_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    queue = session.debugger_queue
    try:
        async for output in _consume_queue(queue):
            await websocket.send_text(output or "")
    except WebSocketDisconnect:
        return


@ws_router.websocket("/ws/chat/{session_id}")
async def chat_stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        session = session_manager.get_session(session_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    queue = session.chat_queue
    try:
        async for message in _consume_queue(queue):
            await websocket.send_text(message or "")
    except WebSocketDisconnect:
        return

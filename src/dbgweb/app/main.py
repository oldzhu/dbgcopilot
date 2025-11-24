"""FastAPI entry point for the dbgweb browser UI."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router as api_router
from .ws.routes import ws_router


app = FastAPI(title="Debugger Copilot", version="0.1.0")


def _static_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parent.parent / "static"


static_dir = _static_dir()
if not static_dir.exists():
    raise RuntimeError(f"Static directory not found: {static_dir}")

# Serve static assets (JS/CSS) under /static; index is served via a dedicated route.
app.mount("/static", StaticFiles(directory=static_dir, html=False), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_root() -> HTMLResponse:
    """Serve the single-page application shell."""
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))


app.include_router(api_router)
app.include_router(ws_router)

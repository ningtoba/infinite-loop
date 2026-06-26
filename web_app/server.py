"""FastAPI web server for the Hermes Loop web UI."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
    FileResponse,
)
from fastapi.staticfiles import StaticFiles

from .config_manager import (
    CONFIG_DEFAULTS,
    CONFIG_GROUPS,
    get_config_with_defaults,
    read_env_file,
    write_env_file,
    build_cli_args,
)
from .loop_manager import LoopManager, get_loop_manager

# Determine static directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# SSE client tracking
_sse_clients: list[asyncio.Queue] = []

app = FastAPI(
    title="Hermes Loop Web UI",
    description="Web interface for managing the Infinite Loop Daemon",
    version="1.0.0",
)

# Mount static files after app creation
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _get_env_path() -> str:
    """Get the .env file path."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_dir, ".env")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Hermes Loop Web UI</h1><p>Static files not found.</p>")


# ── Config API ──────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Get the full configuration with current values."""
    env_path = _get_env_path()
    config = get_config_with_defaults(env_path)
    return {
        "groups": CONFIG_GROUPS,
        "config": config,
    }


@app.get("/api/config/groups")
async def get_config_groups():
    """Get config groups (lightweight)."""
    return {"groups": CONFIG_GROUPS}


@app.get("/api/config/raw")
async def get_raw_config():
    """Get raw .env key-value pairs."""
    env_path = _get_env_path()
    return {"config": read_env_file(env_path)}


@app.post("/api/config")
async def save_config(request: Request):
    """Save configuration values to .env file."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    env_path = _get_env_path()
    write_env_file(env_path, data)
    return {"success": True, "message": "Configuration saved"}


@app.get("/api/config/cli-preview")
async def preview_cli_args():
    """Preview the CLI arguments that would be used to start the daemon."""
    env_path = _get_env_path()
    config = read_env_file(env_path)
    cli_args = build_cli_args(config)
    return {"args": cli_args, "command": "python3 -m hermes_loop " + " ".join(cli_args)}


# ── Loop Control API ────────────────────────────────────────────────────────

@app.post("/api/loop/start")
async def start_loop():
    """Start the infinite loop daemon."""
    manager = get_loop_manager(_get_env_path())
    result = await manager.start()
    if result.get("success"):
        # Broadcast status update
        await _broadcast_sse({"type": "status", "status": "running"})
    return result


@app.post("/api/loop/stop")
async def stop_loop():
    """Stop the infinite loop daemon."""
    manager = get_loop_manager()
    result = await manager.stop()
    if result.get("success"):
        await _broadcast_sse({"type": "status", "status": "stopped"})
    return result


@app.post("/api/loop/pause")
async def pause_loop():
    """Pause the infinite loop daemon."""
    manager = get_loop_manager()
    result = await manager.pause()
    if result.get("success"):
        await _broadcast_sse({"type": "status", "status": "paused"})
    return result


@app.post("/api/loop/resume")
async def resume_loop():
    """Resume the infinite loop daemon."""
    manager = get_loop_manager()
    result = await manager.resume()
    if result.get("success"):
        await _broadcast_sse({"type": "status", "status": "running"})
    return result


# ── Status / Monitoring API ─────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Get combined loop and ledger status."""
    manager = get_loop_manager()
    return manager.get_status()


@app.get("/api/ledger")
async def get_ledger():
    """Get the full ledger state."""
    manager = get_loop_manager()
    return manager.get_ledger()


@app.get("/api/iterations")
async def get_iterations(limit: int = 50, offset: int = 0):
    """Get iteration history."""
    manager = get_loop_manager()
    ledger = manager.get_ledger()
    iterations = ledger.get("iterations", [])
    total = len(iterations)

    # Return most recent first
    iterations = list(reversed(iterations))
    page = iterations[offset : offset + limit]

    return {
        "iterations": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """Get recent daemon logs."""
    manager = get_loop_manager()
    logs = manager.logs
    return {"logs": logs[-limit:]}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── SSE (Server-Sent Events) ────────────────────────────────────────────────

async def _broadcast_sse(data: dict[str, Any]) -> None:
    """Broadcast an event to all connected SSE clients."""
    payload = json.dumps(data, default=str)
    stale = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            stale.append(q)
    for q in stale:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass


@app.get("/live")
async def sse_stream(request: Request):
    """SSE endpoint for live updates."""
    q: asyncio.Queue = asyncio.Queue(maxsize=32)
    _sse_clients.append(q)

    async def event_generator():
        try:
            # Send initial status
            manager = get_loop_manager()
            initial = {
                "type": "init",
                "data": manager.get_status(),
            }
            yield f"event: init\ndata: {json.dumps(initial, default=str)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: update\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat', 'time': datetime.now(timezone.utc).isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                _sse_clients.remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Background status poller for SSE ────────────────────────────────────────

async def _status_poller():
    """Poll the ledger and broadcast changes to SSE clients."""
    manager = get_loop_manager()
    last_hash = ""
    while True:
        await asyncio.sleep(2)
        if not _sse_clients:
            continue
        try:
            status = manager.get_status()
            current_hash = str(status.get("ledger", {}).get("total_iterations", 0))
            if current_hash != last_hash:
                last_hash = current_hash
                await _broadcast_sse({
                    "type": "status_update",
                    "data": status,
                })
        except Exception:
            pass


@app.on_event("startup")
async def startup():
    """Start background tasks on server startup."""
    asyncio.create_task(_status_poller())


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    """Entry point for the web app."""
    import uvicorn

    import argparse

    parser = argparse.ArgumentParser(description="Hermes Loop Web UI Server")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to bind to (default: 8080)"
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Path to .env file (default: auto-detect)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (development)"
    )
    args = parser.parse_args()

    # Set env path if provided
    if args.env:
        os.environ["HERMES_LOOP_ENV_PATH"] = args.env

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Hermes Loop Web UI                           ║")
    print(f"║  Starting server on {args.host}:{args.port}                        ║")
    print(f"╚══════════════════════════════════════════════╝")

    uvicorn.run(
        "web_app.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()

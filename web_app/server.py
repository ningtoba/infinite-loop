"""FastAPI web server for the Hermes Loop web UI."""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from .config_manager import (
    CONFIG_GROUPS,
    CONFIG_PATH,
    get_config_with_defaults,
    get_raw_config,
    write_json_config,
    build_cli_args,
)
from .loop_manager import get_loop_manager

# Determine static directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# SSE client tracking
_sse_clients: list[asyncio.Queue] = []
_sse_clients_lock = asyncio.Lock()
# Hold references to background tasks to prevent GC from cancelling them
_background_tasks: set[asyncio.Task] = set()

app = FastAPI(
    title="Hermes Loop Web UI",
    description="Web interface for managing the Infinite Loop Daemon",
    version="1.0.0",
)

# Mount static files after app creation
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    config = get_config_with_defaults()
    return {
        "groups": CONFIG_GROUPS,
        "config": config,
        "config_path": CONFIG_PATH,
    }


@app.get("/api/config/groups")
async def get_config_groups():
    """Get config groups (lightweight)."""
    return {"groups": CONFIG_GROUPS}


@app.get("/api/config/raw")
async def get_raw_config_api():
    """Get raw key-value config."""
    return {"config": get_raw_config()}


@app.post("/api/config")
async def save_config(request: Request):
    """Save configuration values to JSON config file."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None

    write_json_config(data)
    return {"success": True, "message": "Configuration saved", "path": CONFIG_PATH}


@app.get("/api/config/cli-preview")
async def preview_cli_args():
    """Preview the CLI arguments that would be used to start the daemon."""
    config = get_raw_config()
    cli_args = build_cli_args(config)
    return {"args": cli_args, "command": "hermes_loop " + " ".join(cli_args)}


# ── Loop Control API ────────────────────────────────────────────────────────


@app.post("/api/loop/start")
async def start_loop():
    """Start the infinite loop daemon."""
    manager = get_loop_manager()
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


@app.post("/api/loop/reset")
async def reset_ledger():
    """Reset the ledger — deletes iteration history so the next start is fresh."""
    ledger_path = "/tmp/infinite-loop-state.json"
    lock_path = "/tmp/infinite-loop-state.lock"
    try:
        if os.path.exists(ledger_path):
            os.remove(ledger_path)
        if os.path.exists(lock_path):
            os.remove(lock_path)
        return {"success": True, "message": "Ledger reset — next start will be fresh"}
    except OSError as e:
        return {"success": False, "error": str(e)}


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
    async with _sse_clients_lock:
        stale = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except Exception:
                stale.append(q)
        for q in stale:
            try:
                _sse_clients.remove(q)
            except ValueError:
                pass


@app.get("/live")
async def sse_stream(request: Request):
    """SSE endpoint for live updates."""
    q: asyncio.Queue = (
        asyncio.Queue()
    )  # unbounded — prevents QueueFull errors during burst updates
    async with _sse_clients_lock:
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
            async with _sse_clients_lock:
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
    """Poll the ledger and broadcast changes + new log entries to SSE clients."""
    manager = get_loop_manager()
    last_log_count = 0
    last_status_hash = ""
    idle_ticks = 0
    while True:
        await asyncio.sleep(2)
        if not _sse_clients:
            idle_ticks = 0
            continue
        try:
            status = manager.get_status()
            live = status.get("live_iteration", {})

            # Build a richer hash covering iteration number, worker statuses,
            # error_counts, mitigations, log count, terminal lines, and
            # latest iteration details (worktree merge, summary changes).
            iter_n = live.get("n", 0)
            worker_statuses = "|".join(
                f"{w.get('id','')}:{w.get('status','')}"
                for w in live.get("workers", [])
            )
            err_counts = str(status.get("error_counts", {}))
            mitigations = str(status.get("mitigations", {}))
            term_total = sum(len(v) for v in status.get("worker_term", {}).values())
            log_count = len(status.get("recent_logs", []))
            # Include latest iteration's key fields so WT changes (worktree_merge,
            # summary, error, classification) trigger SSE pushes.
            latest = status.get("latest_iteration", {}) or {}
            latest_sig = "|".join(
                [
                    str(latest.get("n", 0)),
                    str(latest.get("worktree_merge", {})),
                    str(latest.get("error", "")),
                    str(latest.get("classification", "")),
                    str(latest.get("summary", "")[:60]),
                ]
            )

            status_hash = "|".join(
                [
                    str(iter_n),
                    worker_statuses,
                    err_counts,
                    mitigations,
                    str(term_total),
                    str(log_count),
                    latest_sig,
                ]
            )

            if status_hash != last_status_hash:
                last_status_hash = status_hash
                idle_ticks = 0
                await _broadcast_sse({"type": "status_update", "data": status})
            elif idle_ticks >= 5:  # every ~10s, push a keepalive status
                idle_ticks = 0
                await _broadcast_sse({"type": "status_update", "data": status})
            else:
                idle_ticks += 1
            # Push new log entries individually
            logs = status.get("recent_logs", [])
            for i in range(last_log_count, len(logs)):
                await _broadcast_sse({"type": "log_entry", "entry": logs[i]})
            last_log_count = len(logs)
        except Exception:
            pass


@app.on_event("startup")
async def startup():
    """Start background tasks on server startup."""
    task = asyncio.create_task(_status_poller())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.on_event("shutdown")
async def shutdown():
    """Clean up background tasks on server shutdown."""
    for task in set(_background_tasks):
        task.cancel()
    if _background_tasks:
        # Use wait() with timeout instead of gather() — _status_poller is
        # an infinite loop that never finishes on its own. Cancel + wait
        # with timeout ensures we don't hang the server shutdown.
        done, pending = await asyncio.wait(
            _background_tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED
        )
        # Cancel any tasks that didn't finish in time
        for task in pending:
            task.cancel()
    _background_tasks.clear()


# ── Entry point ─────────────────────────────────────────────────────────────


def main():
    """Entry point for the web app."""
    import uvicorn

    import argparse

    default_port = int(os.environ.get("WEB_PORT", "8090"))

    parser = argparse.ArgumentParser(description="Hermes Loop Web UI Server")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"Port to bind to (default: {default_port})",
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

    print("╔══════════════════════════════════════════════╗")
    print("║  Hermes Loop Web UI                           ║")
    print(f"║  Starting server on {args.host}:{args.port}                        ║")
    print("╚══════════════════════════════════════════════╝")

    uvicorn.run(
        "web_app.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()

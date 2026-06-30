"""FastAPI web server for the omp-loop web UI."""

import asyncio
import contextlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from omp_loop.config import LEDGER_PATH, LOCK_PATH
from omp_loop.config_file import CONFIG_PATH

from .config_manager import (
    CONFIG_GROUPS,
    build_cli_args,
    get_config,
    get_raw_config,
    save_config,
    validate_config,
)
from .loop_manager import get_loop_manager
from .rate_limiter import SlidingWindowRateLimiter

# Determine static directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# # SSE client tracking
_sse_clients: list[asyncio.Queue] = []
_sse_clients_lock = asyncio.Lock()

# Server start timestamp for uptime reporting
_server_start_time: float = 0.0

# API key read once at startup (SEC-004), not from os.environ on every request.
# Set by main() on initial launch; empty string means auth is disabled.
_API_KEY: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────


def _read_file(path: str) -> str:
    """Read a text file — separated for use with asyncio.to_thread."""
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read file %s: %s", path, e)
        raise


# Module-level logger
logger = logging.getLogger(__name__)


# ── Rate limiters ──────────────────────────────────────────────────────────

app = FastAPI(
    title="omp-loop Web UI",
    description="Web interface for managing the Infinite Loop Daemon",
    version="1.0.0",
)


# ── Rate limiters ──────────────────────────────────────────────────────────

# Control endpoints (POST start/stop/pause/resume/reset/config-write): 30 req/min
_control_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60.0)
# Read-only endpoints (GET /api/*): 120 req/min
_read_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60.0)


# ── API-Key Authentication Middleware ─────────────────────────────────────


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Validate `Authorization: Bearer <key>` on /api/* routes.

    Skips the health-check endpoint (/api/health) and all non-/api paths.
    Uses the module-level _API_KEY constant set once at startup by main().
    Falls back to os.environ for backward compat with tests that patch
    the environment directly without going through main().
    When the key is empty, auth is disabled entirely, preserving
    backward compat for local development.
    """
    # Only use the startup-captured key, not os.environ (SEC-004)
    if not _API_KEY:
        # No key configured — allow all requests (local-dev mode)
        return await call_next(request)

    path = request.url.path

    # Only enforce on /api/* routes
    if not path.startswith("/api/"):
        return await call_next(request)

    # Always allow health checks and SSE streams (EventSource can't send auth headers)
    if path in ("/api/health", "/api/live", "/api/sse/stream"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {_API_KEY}"

    if auth_header != expected:
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid API key"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)


# ── Rate-Limiting Middleware ──────────────────────────────────────────────────


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply sliding-window rate limits to /api/* routes.

    Control endpoints (POST /api/config, /api/loop/*): 30 req/min.
    Read-only endpoints (GET /api/*): 120 req/min.
    Exempt: /api/health, all non-/api paths.

    Rate limiting uses a sliding window per client IP and is independent
    of authentication — it applies even when OMP_LOOP_API_KEY is unset.
    """
    path = request.url.path

    # Only enforce on /api/* routes
    if not path.startswith("/api/"):
        return await call_next(request)

    # Always allow health checks
    if path == "/api/health":
        return await call_next(request)

    # Classify the endpoint and pick the right limiter
    method = request.method

    # Control: POST /api/config or POST /api/loop/*
    is_control = method == "POST" and (path == "/api/config" or path.startswith("/api/loop/"))
    # Read: GET any /api/* path
    is_read = method == "GET"

    if is_control:
        limiter = _control_limiter
        limit_count = 30
    elif is_read:
        limiter = _read_limiter
        limit_count = 120
    else:
        # Unclassified method/path combination — let it through
        return await call_next(request)

    # Determine client IP
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "127.0.0.1"

    if not await limiter.check(client_ip):
        retry_after = 60  # window_seconds is always 60 for both limiters
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={"Retry-After": str(retry_after)},
        )

    remaining = await limiter.remaining(client_ip)
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit_count)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


# CORS — restrict to localhost by default for security.
# Override via OMP_LOOP_CORS_ORIGINS env var (comma-separated) for
# production deployments that need cross-origin access.
_cors_origins = os.environ.get(
    "OMP_LOOP_CORS_ORIGINS",
    "http://localhost:8090",
).split(",")
logger = logging.getLogger(__name__)

# Validate CORS origins — reject wildcard "*" in production, warn for permissive values.
_cleaned_origins: list[str] = []
for origin in _cors_origins:
    stripped = origin.strip()
    if stripped == "*":
        logger.warning(
            "CORS origin '*' is permissive and should not be used in production. "
            "Set OMP_LOOP_CORS_ORIGINS to a comma-separated list of explicit origins."
        )
    _cleaned_origins.append(stripped)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cleaned_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Security Headers Middleware ───────────────────────────────────────────────
# Registered after CORS (outermost) so it runs first in the middleware stack
# and adds headers to ALL responses including 401/429 from inner middleware.


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add defense-in-depth HTTP security headers.

    Sets Content-Security-Policy, X-Frame-Options, X-Content-Type-Options,
    and X-XSS-Protection on every response. Designed to mitigate XSS,
    clickjacking, and MIME-sniffing attacks even if inner middleware
    or endpoint code has a vulnerability.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"  # Deprecated but suppresses legacy warnings
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss:; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )
    return response


# Mount static files after app creation
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web UI (PERF-001: use asyncio.to_thread for blocking I/O)."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    exists = await asyncio.to_thread(os.path.exists, index_path)
    if exists:
        try:
            content = await asyncio.to_thread(_read_file, index_path)
            return HTMLResponse(content)
        except OSError as e:
            logger.warning("Failed to read static index.html: %s", e)
            return HTMLResponse("<h1>omp-loop Web UI</h1><p>Static files not found.</p>")
    return HTMLResponse("<h1>omp-loop Web UI</h1><p>Static files not found.</p>")


# ── Config API ──────────────────────────────────────────────────────────────


@app.get("/api/config")
async def get_config_api():
    """Get the full configuration with current values."""
    config = get_config()
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
async def save_config_api(request: Request):
    """Save configuration values to JSON config file.
    Validates the config before persisting (SECURITY-001).
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None

    # Validate config before saving
    result = validate_config(data)
    if not result["valid"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "Configuration validation failed", "errors": result["errors"]},
        )

    save_config(data)
    return {"success": True, "message": "Configuration saved", "path": CONFIG_PATH}


@app.get("/api/config/cli-preview")
async def preview_cli_args():
    """Preview the CLI arguments that would be used to start the daemon."""
    config = get_raw_config()
    cli_args = build_cli_args(config)
    return {"args": cli_args, "command": "python3 -m omp_loop " + " ".join(cli_args)}


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
    try:
        await asyncio.to_thread(_reset_ledger_files)
        return {"success": True, "message": "Ledger reset — next start will be fresh"}
    except OSError as e:
        return {"success": False, "error": str(e)}


def _reset_ledger_files():
    """Synchronous helper for reset_ledger, offloaded to thread pool."""
    if os.path.exists(LEDGER_PATH):
        os.remove(LEDGER_PATH)
    if os.path.exists(LOCK_PATH):
        os.remove(LOCK_PATH)


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
    """Get iteration history (PERF-002: capped at 500 max limit)."""
    # Cap limit to prevent OOM on large ledgers
    limit = min(max(limit, 1), 500)
    if offset < 0:
        offset = 0

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
    """Health check endpoint.

    Returns basic service health, version, and uptime.
    Exempt from API-key auth and rate limiting.
    Designed for container orchestrators, load balancers,
    and monitoring systems — always returns 200 when alive.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": time.monotonic() - _server_start_time if _server_start_time > 0 else None,
    }


# ── System Resources ─────────────────────────────────────────────────────────


# CPU delta tracking for accurate utilization (L-4: threading.Lock for concurrent reads)
_cpu_lock = threading.Lock()
_last_cpu_total: int | None = None
_last_cpu_idle: int | None = None
_last_cpu_time: float = 0.0

# Pre-warm: read /proc/stat twice at import to seed the first delta
for _i in range(2):
    try:
        with open("/proc/stat") as _f:
            _parts = _f.readline().split()
        if len(_parts) >= 5:
            _idle = int(_parts[4])
            _total = sum(int(_p) for _p in _parts[1:] if _p.isdigit())
            _now = time.monotonic()
            if _last_cpu_total is not None:
                break
            _last_cpu_total = _total
            _last_cpu_idle = _idle
            _last_cpu_time = _now
    except (OSError, ValueError):
        break


def _get_cpu_percent():
    """Get CPU usage percentage from /proc/stat using delta between reads."""
    global _last_cpu_total, _last_cpu_idle, _last_cpu_time
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        if len(parts) < 5:
            return 0.0
        idle = int(parts[4])
        total = sum(int(p) for p in parts[1:] if p.isdigit())
        now = time.monotonic()

        with _cpu_lock:
            if _last_cpu_total is not None and _last_cpu_idle is not None:
                delta_total = total - _last_cpu_total
                delta_idle = idle - _last_cpu_idle
                _last_cpu_total = total
                _last_cpu_idle = idle
                _last_cpu_time = now
                if delta_total > 0:
                    return round(100.0 * (delta_total - delta_idle) / delta_total, 1)
            else:
                # First read — no delta yet
                _last_cpu_total = total
                _last_cpu_idle = idle
                _last_cpu_time = now
                return None
        return 0.0
    except (OSError, ValueError):
        return 0.0


def _get_memory_info():
    """Get memory info from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_str = parts[1].strip().split()[0] if parts[1].strip() else "0"
                    if val_str.isdigit():
                        meminfo[key] = int(val_str) * 1024
        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0) or meminfo.get("MemFree", 0)
        used = total - available
        percent = round(100 * used / total, 1) if total > 0 else 0
        return {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "percent": percent,
        }
    except (OSError, ValueError, KeyError):
        return {"total_bytes": 0, "used_bytes": 0, "available_bytes": 0, "percent": 0}


def _get_disk_info():
    """Get disk usage."""
    try:
        import shutil

        usage = shutil.disk_usage("/")
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent": round(100 * usage.used / usage.total, 1),
        }
    except (OSError, PermissionError):
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "percent": 0}


@app.get("/api/system")
async def system_resources():
    """Get system resource usage."""
    cpu_percent = await asyncio.to_thread(_get_cpu_percent)
    if cpu_percent is None:
        cpu_percent = 0.0
    return {
        "cpu_percent": cpu_percent,
        "memory": await asyncio.to_thread(_get_memory_info),
        "disk": await asyncio.to_thread(_get_disk_info),
    }


# ── SSE (Server-Sent Events) ────────────────────────────────────────────────


async def _broadcast_sse(data: dict[str, Any]) -> None:
    """Broadcast an event to all connected SSE clients."""
    payload = json.dumps(data, default=str)
    async with _sse_clients_lock:
        stale = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                stale.append(q)
        for q in stale:
            with contextlib.suppress(ValueError):
                _sse_clients.remove(q)


async def _sse_stream_impl(request: Request):
    """SSE endpoint implementation shared by /api/live and /live."""
    q: asyncio.Queue = asyncio.Queue(maxsize=512)

    async def event_generator():
        # Only register queue when the generator actually starts (M-3).
        # If the client disconnects before this runs, the queue is never orphaned.
        async with _sse_clients_lock:
            _sse_clients.append(q)

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
                    heartbeat = json.dumps(
                        {"type": "heartbeat", "time": datetime.now(timezone.utc).isoformat()},
                        default=str,
                    )
                    yield f"event: heartbeat\ndata: {heartbeat}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            async with _sse_clients_lock:
                with contextlib.suppress(ValueError):
                    _sse_clients.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/live")
@app.get("/api/sse/stream")
async def sse_stream_api(request: Request):
    """SSE endpoint for live updates (canonical path under /api)."""
    return await _sse_stream_impl(request)


@app.get("/live")
async def sse_stream_legacy(request: Request):
    """SSE endpoint for live updates (legacy path, kept for backward compat)."""
    return await _sse_stream_impl(request)


# ── Background status poller for SSE ────────────────────────────────────────


async def _status_poller():
    """Poll the ledger and broadcast changes + new log entries to SSE clients.
    Early-returns if no SSE clients are connected (PERF-003).
    """
    manager = get_loop_manager()
    last_log_count = 0
    last_status_hash = ""
    idle_ticks = 0
    while True:
        await asyncio.sleep(2)
        if not _sse_clients:
            # Don't reset last_log_count — when clients reconnect, they get
            # full status via the init event.  Only reset the hash so the
            # first status after reconnect is broadcast regardless.
            last_status_hash = ""
            await asyncio.sleep(1)  # Quick retry when idle
            continue
        try:
            status = await manager.async_get_status()
            live = status.get("live_iteration", {})
        except Exception:
            await asyncio.sleep(5)
            continue
        try:
            # Build a richer hash covering iteration number, worker statuses,
            # error_counts, mitigations, log count, terminal lines, and
            # latest iteration details (worktree merge, summary changes).
            iter_n = live.get("n", 0)
            worker_statuses = "|".join(f"{w.get('id', '')}:{w.get('status', '')}" for w in live.get("workers", []))
            err_counts = str(status.get("error_counts", {}))
            mitigations = str(status.get("mitigations", {}))
            worker_term = status.get("worker_term", {})
            # Hash the last 3 lines of each worker to detect content changes
            term_content_hash = "".join("".join(lines[-3:]) for _, lines in sorted(worker_term.items()))
            log_count = len(status.get("recent_logs", []))
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
                    term_content_hash,
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
        except (json.JSONDecodeError, OSError, KeyError) as e:
            manager._add_log("warn", f"Status poller error: {e}")


@app.on_event("startup")
async def startup():
    """Start background tasks on server startup."""
    global _server_start_time
    _server_start_time = time.monotonic()
    asyncio.create_task(_status_poller())


# ── Entry point ─────────────────────────────────────────────────────────────


def main():
    """Entry point for the web app."""
    import argparse

    import uvicorn

    global _API_KEY

    try:
        default_port = int(os.environ.get("WEB_PORT", "8090"))
    except (ValueError, TypeError):
        default_port = 8090

    parser = argparse.ArgumentParser(description="omp-loop Web UI Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0) — all interfaces")
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
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")
    args = parser.parse_args()

    # Read API key once at startup (SEC-004) — closes over os.environ so
    # per-request middleware never reads env vars.
    _raw_key = os.environ.get("OMP_LOOP_API_KEY", "")
    if _raw_key:
        _API_KEY = _raw_key
        print("  [AUTH] API key authentication enabled")
    else:
        _API_KEY = ""
        print("  [AUTH] API key authentication disabled (local-dev mode)")

    # Set env path if provided
    if args.env:
        os.environ["OMP_LOOP_ENV_PATH"] = args.env

    print("╔══════════════════════════════════════════════╗")
    print("║  omp-loop Web UI                           ║")
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

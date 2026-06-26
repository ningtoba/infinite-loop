# Research: High-Impact Features for Infinite-Loop Daemon (v11.6.1 → v12.0.0)

Research date: 2026-06-26
Focus: Adding features with **zero external pip dependencies** (Python stdlib only)

> **Implemented in v11.9.0** (iteration #5): Pushbullet and ntfy push notification
> support (`--notify-pushbullet`, `--notify-ntfy`, `--notify-ntfy-server`). These are
> stdlib-only using `urllib.request` — no external dependencies, no API keys required
> for ntfy (uses public ntfy.sh by default; self-hosted supported).

> **Implemented in v11.8.0** (iteration #4): Preflight health checks (`--preflight`, `--preflight-fail-fast`),
> `/api/status` JSON API endpoint, REST API control endpoints (`POST /control/stop`,
> `POST /control/pause`, `POST /control/resume`), and Status Dashboard v2 improvements
> (auto-refresh, inline SVG favicon, system resource cards, ETA column, cooldown indicator,
> dark/light mode via prefers-color-scheme).

## Implementation Status

| Feature | Status | Version |
|---------|--------|---------|
| Config file support (TOML + JSON) | ✅ DONE in v11.7.0 | v11.7.0 |
| Desktop notifications (notify-send) | ✅ DONE in v11.7.0 | v11.7.0 |
| Startup delay | ✅ DONE in v11.7.0 | v11.7.0 |
| Error classification | ✅ DONE in v11.7.0 | v11.7.0 |
| Daemon status API (/api/status) | ✅ DONE in v11.8.0 | v11.8.0 |
| REST API control endpoints (stop/pause/resume) | ✅ DONE in v11.8.0 | v11.8.0 |
| Preflight health checks | ✅ DONE in v11.8.0 | v11.8.0 |
| Status dashboard v2 (auto-refresh, system stats, ETA, cooldown, favicon) | ✅ DONE in v11.8.0 | v11.8.0 |
| Completion notification | ✅ DONE in v11.7.0 | v11.7.0 |
| Pushbullet/ntfy push notifications | ✅ DONE in v11.9.0 (iteration #5) | v11.9.0 |
| CLI tab completion | 🔲 NOT IMPLEMENTED | v12.0.0 |

## Current Architecture Summary

- **~3750 lines** in `scripts/launch-loop.py` (single-file daemon)
- **~50 CLI flags** via `argparse`
- Already has: webhook server (http.server), file watcher (os.stat polling), log rotation (RotatingFileHandler), status HTML dashboard (inline template), ETA tracking, structured output validation (manual JSON Schema subset), resource tracking (/proc), convergence detection (Jaccard word similarity), adaptive cooldown, git diff storage, multi-worker context merging
- Session-self-loop.py: 424-line companion for in-session execution
- Stdlib imports used: `argparse`, `fcntl`, `http.server`, `io`, `json`, `logging`, `logging.handlers`, `os`, `pathlib`, `select`, `shlex`, `shutil`, `signal`, `socket`, `socketserver`, `subprocess`, `sys`, `threading`, `time`, `urllib.parse`, `urllib.request`, `concurrent.futures`, `datetime`, `re`

---

## 1. Config File Support (JSON / TOML / INI) — ✅ IMPLEMENTED v11.7.0

### Stdlib Options

| Format | Stdlib Module | Pros | Cons |
|--------|--------------|------|------|
| **TOML** | `tomllib` (Python 3.11+) | Modern, well-specified, supports nested config, comments, tables | Read-only (no write), min Python 3.11 |
| **INI** | `configparser` (always available) | Mature, widespread, read+write, interpolation | Flat structure, types are strings, no nested lists/dicts naturally |
| **JSON** | `json` (always available) | Already used for ledger, trivial to implement | No comments, trailing comma errors |
| **YAML** | ❌ **Not in stdlib** | — | Requires `PyYAML` — breaks zero-dep constraint |

### Recommendation: JSON + TOML (implemented as JSON only)

---

## 2. Preflight Health Checks — ✅ IMPLEMENTED v11.8.0

### What exists now
- Hermes binary check (`find_hermes()` + `shutil.which`) — but it's a **warning**, not a hard stop
- Worker URL health check (when `--worker-url auto`, pings `/health` endpoint)

### What was implemented
- `--preflight` flag runs comprehensive checks before the loop starts
- `--preflight-fail-fast` stops on the first failure instead of collecting all results
- Prints a formatted table with ✓/✗ indicators
- Checks: hermes binary, workdir, git repo, sentinel writable, port available, context/goals files, output schema file, disk space

---

## 3. REST API for External Control — ✅ IMPLEMENTED v11.8.0

### What exists now
- Webhook server (`http.server`): GET `/health`, GET `/status`, POST `/webhook`
- Sentinel file: `echo "stop|pause|resume" > /tmp/infinite-loop-stop`

### What was implemented

```
GET    /api/status          → Full iteration state as JSON (complete ledger dump)
POST   /control/stop        → Write "stop" to sentinel file
POST   /control/pause       → Write "pause" to sentinel file  
POST   /control/resume      → Write "resume" to sentinel file (or delete it)
```

---

## 4. Notification Integration — ✅ IMPLEMENTED v11.9.0 (iteration #5)

### What exists now (v11.7.0+)
- Desktop notifications via notify-send (`--notify-desktop`, `--notify-on-completion`)

### What was implemented in v11.9.0

1. **Pushbullet support** (`--notify-pushbullet TOKEN`) — Sends iteration results
   to your phone via Pushbullet. Uses the Pushbullet API v2 POST /pushes endpoint
   with stdlib urllib only. Get your API token at https://www.pushbullet.com/#settings.
   Each iteration sends a "Infinite Loop Iteration" push with summary and duration.
   Completion sends "Infinite Loop Complete" with full stats.

2. **ntfy support** (`--notify-ntfy TOPIC`) — Sends push notifications via ntfy.sh
   (or any self-hosted ntfy server). No API key required for public ntfy.sh.
   Uses ntfy's simple HTTP PUT API. Configure a custom server URL with
   `--notify-ntfy-server https://your-server.com`.

3. **Pushbullet/ntfy in completion notification** — Both `--notify-on-completion`
   and `--notify-pushbullet`/`--notify-ntfy` send final summary notifications when
   the daemon finishes.

### Example Usage

```bash
python3 scripts/launch-loop.py \\
  --goal "Fix type errors" \\
  --notify-pushbullet "o.abc123def456..." \\
  --notify-ntfy "my-loop-alerts" \\
  --notify-ntfy-server "https://ntfy.sh" \\
  --run
```

### API Details

| Service | Auth | Flag | URL |
|---------|------|------|-----|
| Pushbullet | API access token | `--notify-pushbullet` | POST https://api.pushbullet.com/v2/pushes |
| ntfy.sh | None (public) | `--notify-ntfy` | PUT https://ntfy.sh/{topic} |
| ntfy (self-hosted) | None or basic auth | `--notify-ntfy-server` + `--notify-ntfy` | PUT {server}/{topic} |

## 5. Status Dashboard Improvements — ✅ IMPLEMENTED v11.8.0

### What was implemented

1. **Auto-refresh** via `<meta http-equiv="refresh" content="30">` tag
2. **Inline SVG favicon** (infinity symbol emoji, base64-encoded)
3. **System resources** (CPU seconds, memory MB, memory %) from iteration data
4. **ETA column** showing estimated time remaining
5. **Cooldown indicator** showing current cooldown time
6. **Dark/light mode** via CSS `prefers-color-scheme`

---

## 6. CLI Improvements — Tab Completion — 🔲 NOT YET IMPLEMENTED

---

## Summary: Prioritization & Effort

| Feature | Effort | Dependencies | Impact | Priority | Status |
|---------|--------|-------------|--------|----------|--------|
| **Preflight health checks** | 3-4h | None | High — prevents "first iteration fails" | ★★★★★ | ✅ DONE |
| **Config file** | 2-3h | `json` (stdlib) | High — reusable configs | ★★★★★ | ✅ DONE (v11.7.0) |
| **REST API control endpoints** | 2-3h | None (http.server) | Medium — sentinel already works | ★★★ | ✅ DONE |
| **Dashboard improvements** | 2h | None | Medium — already functional; auto-refresh + system stats | ★★★ | ✅ DONE |
| **Completion notification** | 1h | None | Medium — already functional via notify-send | ★★★ | ✅ DONE (v11.7.0) |
| **Pushbullet/ntfy notifications** | 2-3h | None (urllib) | Medium — mobile notifications | ★★★ | ✅ DONE (v11.9.0) |
| **CLI tab completion** | 1-2h | None (static scripts) | Low — quality-of-life | ★★ | 🔲 PENDING |

### Python Version Requirements
- `tomllib`: Python 3.11+ (safe requirement as of 2026)
- Everything else: Python 3.8+

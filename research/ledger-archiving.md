# In-Process Ledger Archiving — Research & Implementation Plan

**Date:** 2026-06-26  
**Skill:** infinite-loop v11.14.0  
**Objective:** Add automatic archiving of trimmed ledger iterations before they are discarded.

---

## 1. Audit: Where `--keep-iterations` Trims the Ledger

**File:** `scripts/launch-loop.py`  
**Lines 3839–3850** (inside `run_loop()`, near the end of each iteration's bookkeeping section):

```python
# --- Auto-shrink ledger ---
if (
    keep_iterations > 0
    and len(state.get("iterations", [])) > keep_iterations * 2
):
    old_count = len(state["iterations"])
    state["iterations"] = state["iterations"][-keep_iterations:]
    state["total_iterations"] = iteration_count
    _log(
        f"[SHRINK] Trimmed ledger from {old_count} to {keep_iterations} iterations"
    )
    write_ledger(state)
```

**Key observations:**
- Trigger condition: `len(iterations) > keep_iterations * 2` — i.e., trims when size exceeds *double* the keep size (a hysteresis band).
- Action: keeps only the **last** `keep_iterations` entries, discarding the leading ones.
- After trimming, `write_ledger(state)` persists the shrunken state.
- **The discarded entries are permanently lost** — no backup, no archive.
- The trimmed entries are `state["iterations"][0 : old_count - keep_iterations]`.

**Iteration record structure** (lines 3634–3670):
```python
record = {
    "n": iteration_count,
    "task_type": task_type,
    "goal": ...,           # current goal text
    "started_at": ...,     # ISO timestamp
    "completed_at": ...,   # ISO timestamp
    "duration_seconds": total_duration,
    "summary": ...,        # up to 500 chars
    "compacted": bool,
    "error": str | None,
    "exit_code": 0 or 1,
    "toolsets": [...],     # snapshot
    "workers": int | None,
    "worker_results": [...],
    "next_goal": ...,      # evolved next goal
    "next_context": ...,   # context injection
    "spawned_session_id": str | None,
    "output_schema": dict | None,
    "output_validation": dict | None,
    "git_diff": str | None,      # if --store-git-diff
    "system": {...},             # system resource diff
}
```

---

## 2. Design: `_archive_iterations()` Function

### Placement
New function, inserted near `write_ledger()` / `read_ledger()` (around line 1486 in `scripts/launch-loop.py`).

### Signature
```python
def _archive_iterations(
    iterations: list[dict],
    archive_dir: str,
    tag: str = "",
) -> int:
    """
    Archive a list of iteration records to a gzip-compressed JSONL file.

    Args:
        iterations: List of iteration record dicts to archive (oldest-first).
        archive_dir: Directory for archive files (created if needed).
        tag: Optional run tag to embed in the filename.

    Returns:
        Number of iterations archived (0 if nothing to archive).
    """
```

### Algorithm
1. **Guard**: if `iterations` is empty, return 0 immediately.
2. **Filename generation**: determine today's date and sequence number.
3. **Atomically write**: write to `.tmp` file, then rename to final name.
4. **Log**: `_log(f"[ARCHIVE] Saved {len(iterations)} iterations to {filename}")`.
5. **Return** count.

### Detailed implementation
```python
import gzip

def _archive_iterations(
    iterations: list[dict],
    archive_dir: str,
    tag: str = "",
) -> int:
    if not iterations:
        return 0

    os.makedirs(archive_dir, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = 0
    tag_part = f"-{tag}" if tag else ""
    while True:
        seq += 1
        basename = f"iterations-{today}{tag_part}-{seq:04d}.jsonl.gz"
        final_path = os.path.join(archive_dir, basename)
        if not os.path.exists(final_path):
            break
        # If file already exists (same day, same seq), increment seq
        # This handles rapid successive archives within the same second

    tmp_path = final_path + ".tmp"
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
            # First line: metadata header (_meta)
            meta = {
                "_meta": {
                    "version": 1,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(iterations),
                    "iteration_range": {
                        "first": iterations[0].get("n"),
                        "last": iterations[-1].get("n"),
                    },
                    "tag": tag or None,
                }
            }
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            # Data lines: one JSON per iteration
            for it in iterations:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp_path, final_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    _log(
        f"[ARCHIVE] Saved {len(iterations)} iterations to {basename} "
        f"(iter #{iterations[0].get('n')}–#{iterations[-1].get('n')})"
    )
    return len(iterations)
```

---

## 3. File Format: Gzip-Compressed JSONL with Metadata Header

### Specification

**Extension:** `.jsonl.gz`

**Structure (logical after decompression):**

```
# Line 1: metadata (always the first line, key "_meta")
{"_meta": {"version": 1, "archived_at": "2026-06-26T02:35:00+00:00", "count": 500, "iteration_range": {"first": 1, "last": 500}, "tag": "fix-auth"}}

# Lines 2+: one iteration record per line
{"n": 1, "task_type": "research", "goal": "Fix auth bug", ...}
{"n": 2, "task_type": "code-fix", "goal": "Review PR #42", ...}
...
{"n": 500, ...}
```

**Validation:**
- Line 1 MUST have a top-level key `"_meta"` with a dict value containing `"version"` (int).
- Every subsequent line is a JSON object representing a single iteration.
- The file is gzip-compressed end-to-end. `gzip.open()` for both read and write.

**Backward compatibility with replay-ledger.sh** (see §5):
- `replay-ledger.sh` already detects `*.gz` files and uses `zcat` or `gzip -dc` to decompress transparently.
- However, its Python reader does `json.loads(l) for l in sys.stdin if l.strip()` — this will try to parse the `_meta` line as a regular iteration. The `_meta` dict has no `"n"`, `"summary"`, or `"next_goal"` keys, so filter operations will skip it gracefully, but it will be included in the total count.
- **Fix:** Filter out `_meta` lines in the replay script or have `_archive_iterations()` skip the meta line emit.

---

## 4. Directory Structure & Retention Policy

### Directory
```
~/.hermes/infinite-loop-archives/
├── iterations-20260626--0001.jsonl.gz
├── iterations-20260626--0002.jsonl.gz
├── iterations-20260627--0001.jsonl.gz
└── ...
```

Default location: `~/.hermes/infinite-loop-archives/`  
Configurable via `--archive-dir`.

### File naming
```
iterations-{YYYYMMDD}-{tag}-{seq:04d}.jsonl.gz
```
- `{YYYYMMDD}`: date of archiving (UTC).
- `{tag}`: optional run tag, omitted if empty.
- `{seq}`: zero-padded 4-digit sequence number starting at 1, incremented per archive file within the same day.

### Retention policy
- **Default:** keep archives for 30 days.
- Configurable via `--archive-retention N` (0 = keep forever).
- Cleanup runs **after** archiving, inside the same function. It scans `archive_dir` for files matching `iterations-*.jsonl.gz`, parses the date from the filename, and deletes files older than `N` days.
- Cleanup is **best-effort** — failures are logged but do not halt the archiving.
- Cleanup uses `os.path.getmtime()` fallback if filename parsing fails.

### Cleanup implementation
```python
def _cleanup_old_archives(archive_dir: str, retention_days: int) -> None:
    """Remove archive files older than retention_days. Best-effort."""
    if retention_days <= 0:
        return
    if not os.path.isdir(archive_dir):
        return

    cutoff = time.time() - retention_days * 86400
    removed = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".jsonl.gz") or not fname.startswith("iterations-"):
            continue
        fpath = os.path.join(archive_dir, fname)
        try:
            # Try to parse date from filename: iterations-{YYYYMMDD}-...
            date_str = fname.split("-")[1]  # YYYYMMDD
            file_ts = datetime.strptime(date_str, "%Y%m%d").timestamp()
        except (IndexError, ValueError):
            # Fallback to mtime
            try:
                file_ts = os.path.getmtime(fpath)
            except OSError:
                continue
        if file_ts < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError as e:
                _log(f"[ARCHIVE] Failed to remove old archive {fname}: {e}")
    if removed:
        _log(f"[ARCHIVE] Cleaned up {removed} old archive(s)")
```

---

## 5. replay-ledger.sh: Gzip Support Check

**File:** `scripts/replay-ledger.sh`  
**Status:** Already supports `.jsonl.gz` files.

### Existing gzip handling (lines 63–74):
```bash
CAT_CMD="cat"
if [[ "$ARCHIVE_FILE" == *.gz ]]; then
  if command -v zcat &>/dev/null; then
    CAT_CMD="zcat"
  elif command -v gzip &>/dev/null; then
    CAT_CMD="gzip -dc"
  else
    echo "ERROR: cannot read gzipped archive (no zcat/gzip)"
    exit 1
  fi
fi
```

### Issue: The `_meta` line
When the file format includes a `_meta` first line, the script's Python parser:
```python
lines = [json.loads(l) for l in sys.stdin if l.strip()]
```
will successfully parse the meta line as a plain dict. Since it lacks `"n"`, `"summary"`, and `"next_goal"`, the filter (`from_idx`/`to_idx`) will skip it if those keys are absent in the dict's `.get()` calls, but it will still be counted in the total.

### Proposed fix to replay-ledger.sh
Add a filter in the Python inline script to skip `_meta` lines:

```python
lines = [json.loads(l) for l in sys.stdin if l.strip()]
# Skip metadata header line
lines = [l for l in lines if "_meta" not in l]
```

This change should be applied in two places:
1. Line 82: the initial iteration reading.
2. Line 103: the display section.

**Alternatively**, the Python reader can be made archive-aware once and reused. For now, a two-line insertion is sufficient.

---

## 6. Proposed CLI Flags

Three new flags, added after `--keep-iterations` (line 4058):

### `--archive-dir`
```python
parser.add_argument(
    "--archive-dir",
    default=os.path.expanduser("~/.hermes/infinite-loop-archives"),
    help="Directory to store archived iteration files (default: ~/.hermes/infinite-loop-archives)",
)
```

### `--archive-retention`
```python
parser.add_argument(
    "--archive-retention",
    type=int,
    default=30,
    help="Days to keep archived iterations (0=keep forever, default: 30)",
)
```

### `--archive-max-size`
```python
parser.add_argument(
    "--archive-max-size",
    type=int,
    default=0,
    help="Max total size of archive directory in MB before oldest files are purged "
    "(0=unlimited, default: 0). Combined with --archive-retention, the stricter constraint wins.",
)
```

### Flag placement
Insert these three flags right after the `--keep-iterations` flag (after line 4058), before `--run`.

### Propagation
Add parameters to the `run_loop()` function call:
```python
archive_dir=args.archive_dir,
archive_retention=args.archive_retention,
archive_max_size=args.archive_max_size,
```

And to the `run_loop()` signature (after `keep_iterations` at line 3026):
```python
archive_dir: str = "",
archive_retention: int = 30,
archive_max_size: int = 0,
```

### Logging in startup banner
```python
_log(f"  Archive dir:    {archive_dir or 'disabled'}")
_log(f"  Archive retention: {archive_retention}d" if archive_retention > 0 else "  Archive retention: forever")
```

---

## 7. Integration into the Trim Point (Exact Code Change)

### Current code (lines 3839–3850):
```python
        # --- Auto-shrink ledger ---
        if (
            keep_iterations > 0
            and len(state.get("iterations", [])) > keep_iterations * 2
        ):
            old_count = len(state["iterations"])
            state["iterations"] = state["iterations"][-keep_iterations:]
            state["total_iterations"] = iteration_count
            _log(
                f"[SHRINK] Trimmed ledger from {old_count} to {keep_iterations} iterations"
            )
            write_ledger(state)
```

### New code:
```python
        # --- Auto-shrink ledger with archiving ---
        if (
            keep_iterations > 0
            and len(state.get("iterations", [])) > keep_iterations * 2
            and archive_dir
        ):
            old_count = len(state["iterations"])
            # Save discarded iterations before trimming
            discarded = state["iterations"][: old_count - keep_iterations]
            if discarded:
                archived = _archive_iterations(
                    discarded,
                    archive_dir=archive_dir,
                    tag=state.get("tag", ""),
                )
                if archived:
                    _cleanup_old_archives(archive_dir, archive_retention)
                    if archive_max_size > 0:
                        _enforce_archive_max_size(archive_dir, archive_max_size)
            state["iterations"] = state["iterations"][-keep_iterations:]
            state["total_iterations"] = iteration_count
            _log(
                f"[SHRINK] Trimmed ledger from {old_count} to {keep_iterations} iterations"
                f" (archived {len(discarded)} to archive)"
            )
            write_ledger(state)
```

**Note:** The `and archive_dir` guard means archiving is opt-in. If no `--archive-dir` is given (default `~/.hermes/infinite-loop-archives` is set), it always runs when `--keep-iterations` is active. Users who want to disable archiving can pass `--archive-dir ""` explicitly.

---

## 8. Edge Cases & Mitigations

### 8.1 Concurrent Archiving
**Problem:** Two daemon processes could write to the same archive directory concurrently, resulting in filename collisions or corrupted files.  
**Mitigation:**
- The tmp-file-then-rename pattern (`write to .tmp`, `os.replace()`) makes writes **atomic** on the same filesystem.
- The sequence number loop (`while True: ... if not os.path.exists(): break`) prevents filename collision within the same day.
- Use `FileLock` around the archive write and cleanup if true concurrent access is a concern. However, since `run_loop()` is a single-threaded daemon, the only concurrent access scenario is two separate infinite-loop processes sharing the same `--archive-dir`. We use `os.replace()` which is atomic per POSIX.

### 8.2 Disk Full
**Problem:** Writing the archive file fails with `OSError: [Errno 28] No space left on device`.  
**Mitigation:**
- Wrap `_archive_iterations()` and `_cleanup_old_archives()` in try/except.
- On ENOSPC, log a warning (`_log(f"[ARCHIVE] Disk full, archive skipped")`) and **do not crash** the daemon.
- The trimmed iterations are **still discarded** (the ledger shrink proceeds regardless). This is a deliberate trade-off: better to lose the archive than to crash the loop.
- If `--archive-max-size` is set, `_enforce_archive_max_size()` provides a preemptive purge.

### 8.3 Huge Archives
**Problem:** A long-running loop could produce millions of iterations, with a single archive file growing very large.  
**Mitigation:**
- Each archive file covers a **single day** (one file per day, incrementing sequence if multiple trims happen in one day).
- The JSONL format is append-friendly and streamable — even large files can be read incrementally.
- `--archive-max-size` caps the total directory size; oldest files are purged first.
- The metadata header (`_meta.version`, `_meta.count`) provides a fast way to scan archives without decompressing fully.

### 8.4 `_meta` Line Handling in Readers
**Problem:** Existing tools reading `.jsonl.gz` files will encounter the `_meta` first line and may misinterpret it.  
**Mitigation:**
- Update `replay-ledger.sh` to skip `_meta` lines (see §5).
- Document that the first line is metadata in code comments.

### 8.5 Very Large Iteration Records (e.g., git diffs)
**Problem:** With `--store-git-diff`, iteration records can be up to ~10KB each. Archives of 10K iterations could be ~100MB per file.  
**Mitigation:**
- Gzip compression handles this well (typically 5–10× compression for text).
- `--archive-max-size` provides a backstop.
- The daemon only archives during trims, which happen when the in-memory list exceeds `keep_iterations * 2`. With default `keep_iterations=0` (no trim), no archiving occurs. With typical `--keep-iterations 100`, trimming happens at 200 entries — at most 100 entries per archive file.

### 8.6 Tag with Special Characters
**Problem:** The `--tag` value could contain characters invalid in filenames (`/`, `\0`, etc.).  
**Mitigation:** Sanitize the tag by replacing non-alphanumeric characters with `_`:
```python
safe_tag = re.sub(r'[^a-zA-Z0-9_.-]', '_', tag) if tag else ""
```

### 8.7 Corrupted Archive Files
**Problem:** A crash during `gzip.open()` write could leave a `.tmp` file. The atomic rename protects against this (partial file is never at the final path).  
**Mitigation:** The `.tmp` cleanup on exception handles this, and stale `.tmp` files are harmless (they will be skipped by cleanup and replay scripts).

---

## 9. Complete Integration Summary

### Files modified
| File | Change |
|------|--------|
| `scripts/launch-loop.py` | Add `_archive_iterations()`, `_cleanup_old_archives()`, `_enforce_archive_max_size()` near `write_ledger()` |
| `scripts/launch-loop.py` | Add 3 CLI flags after `--keep-iterations` |
| `scripts/launch-loop.py` | Add parameters to `run_loop()` signature |
| `scripts/launch-loop.py` | Replace the trim block (lines 3839–3850) with archive-aware trim |
| `scripts/launch-loop.py` | Pass `archive_dir`, `archive_retention`, `archive_max_size` in the `main()` call to `run_loop()` |
| `scripts/launch-loop.py` | Add `import gzip` and `import re` to imports |
| `scripts/replay-ledger.sh` | Add `_meta` line filter in the Python inline reader (2 places) |

### New imports needed
```python
import gzip          # for gzip.open()
import re            # for tag sanitization
```
`gzip` is stdlib; no new dependencies.

### Default behavior
- If `--keep-iterations` is set (to N > 0) and `--archive-dir` is not explicitly set to `""`, archiving happens automatically to `~/.hermes/infinite-loop-archives/`.
- Archives are retained for 30 days by default.
- To disable archiving: `--archive-dir ""` (or leave `--keep-iterations 0`).
- To keep archives forever: `--archive-retention 0`.
- To cap total archive size: `--archive-max-size 500` (500 MB).

---

## 10. Testing Plan

1. **Unit test `_archive_iterations()`**: Feed a list of 10 records, verify file is created at correct path, has `.jsonl.gz` extension, decompresses to valid JSONL with `_meta` header.
2. **Unit test `_cleanup_old_archives()`**: Create files with old dates, verify deletion.
3. **Integration test**: Run daemon with `--keep-iterations 10 --archive-dir /tmp/test-archive`, let it reach 21 iterations, verify archive file appears and contains exactly the trimmed iterations.
4. **Replay test**: Archive some iterations, then run `replay-ledger.sh` against the archive file and verify it skips `_meta` and replays correctly.
5. **Edge case**: Disk full — simulate with `fill` directory, verify daemon logs warning and continues.

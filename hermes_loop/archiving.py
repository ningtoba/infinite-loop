"""Archiving — archive iterations to gzip-compressed JSONL files."""

import gzip
import json
import os
import re
import time
from datetime import datetime, timezone

from .file_utils import _log


def _archive_iterations(
    iterations: list[dict],
    archive_dir: str,
    tag: str = "",
) -> int:
    """Archive a list of iteration records to a gzip-compressed JSONL file."""
    if not iterations:
        return 0

    os.makedirs(archive_dir, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = 0
    safe_tag = re.sub(r"[^a-zA-Z0-9_.-]", "_", tag) if tag else ""
    tag_part = f"-{safe_tag}" if safe_tag else ""
    while True:
        seq += 1
        basename = f"iterations-{today}{tag_part}-{seq:04d}.jsonl.gz"
        final_path = os.path.join(archive_dir, basename)
        if not os.path.exists(final_path):
            break

    tmp_path = final_path + ".tmp"
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
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
            for it in iterations:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    _log(
        f"[ARCHIVE] Saved {len(iterations)} iterations to {basename} "
        f"(iter #{iterations[0].get('n')}-#{iterations[-1].get('n')})"
    )
    return len(iterations)


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
            date_str = fname.split("-")[1]  # YYYYMMDD
            file_ts = datetime.strptime(date_str, "%Y%m%d").timestamp()
        except (IndexError, ValueError):
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


def _enforce_archive_max_size(archive_dir: str, max_size_mb: int) -> None:
    """Remove oldest archive files until total size is under max_size_mb MB."""
    if max_size_mb <= 0:
        return
    if not os.path.isdir(archive_dir):
        return

    max_bytes = max_size_mb * 1024 * 1024
    files = []
    total_bytes = 0
    for fname in os.listdir(archive_dir):
        if not fname.endswith(".jsonl.gz") or not fname.startswith("iterations-"):
            continue
        fpath = os.path.join(archive_dir, fname)
        try:
            fsize = os.path.getsize(fpath)
            total_bytes += fsize
            files.append((fpath, fsize, fname))
        except OSError:
            continue

    if total_bytes <= max_bytes:
        return

    files.sort(key=lambda x: os.path.getmtime(x[0]))
    removed = 0
    for fpath, fsize, fname in files:
        if total_bytes <= max_bytes:
            break
        try:
            os.remove(fpath)
            total_bytes -= fsize
            removed += 1
            _log(f"[ARCHIVE] Purged {fname} to stay under {max_size_mb}MB limit")
        except OSError as e:
            _log(f"[ARCHIVE] Failed to purge {fname}: {e}")
    if removed:
        _log(f"[ARCHIVE] Purged {removed} archive file(s) to meet max size limit")

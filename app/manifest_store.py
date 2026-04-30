"""Per-assignment JSON manifest (submission times, filenames)."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_manifest_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="manifest_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def manifest_lock_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(manifest_path.suffix + ".rwlock")


def update_manifest(
    manifest_path: Path,
    student_id: str,
    filename: str,
    *,
    replace: bool,
) -> None:
    """Update first upload time only on first submission; refresh last_updated."""
    sid = student_id.strip()
    lock = manifest_lock_path(manifest_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            data = load_manifest(manifest_path)
            now = utc_now_iso()
            prev = data.get(sid)
            if prev and replace:
                first = prev.get("first_upload_at", now)
            elif prev:
                first = prev.get("first_upload_at", now)
            else:
                first = now
            data[sid] = {
                "first_upload_at": first,
                "last_updated_at": now,
                "filename": filename,
            }
            save_manifest_atomic(manifest_path, data)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def remove_student_from_manifest(manifest_path: Path, student_id: str) -> None:
    sid = student_id.strip()
    lock = manifest_lock_path(manifest_path)
    with open(lock, "a+", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            data = load_manifest(manifest_path)
            data.pop(sid, None)
            save_manifest_atomic(manifest_path, data)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def manifest_path_for(storage_root: Path, assignment_id: str) -> Path:
    return storage_root / assignment_id / "_manifest.json"

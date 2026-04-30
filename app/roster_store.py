"""Locked UTF-8 CSV roster read/write (no database)."""
from __future__ import annotations

import csv
import fcntl
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


ROSTER_FIELDS = ["序号", "学院", "专业", "学号", "姓名", "密码哈希"]


def strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _normalize_header_key(key: str | None) -> str:
    k = strip_bom((key or "").strip())
    if k == "":
        return "序号"
    return k


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in row.items():
        nk = _normalize_header_key(k)
        out[nk] = (v or "").strip()
    # Merge duplicate 序号 from empty key and "序号"
    if "序号" not in out and "" in row:
        out["序号"] = str(row.get("") or "").strip()
    return out


def load_roster(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    raw = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(raw.splitlines())
    rows: list[dict[str, str]] = []
    for row in reader:
        norm = _normalize_row(dict(row))
        # Legacy: column 密码 -> ignore plaintext; we only persist 密码哈希
        fixed = {f: norm.get(f, "") for f in ROSTER_FIELDS}
        rows.append(fixed)
    return rows


def save_roster_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="roster_", suffix=".csv", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=ROSTER_FIELDS, lineterminator="\n")
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in ROSTER_FIELDS})
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def update_roster(
    path: Path,
    mutator: Callable[[list[dict[str, str]]], list[dict[str, str]]],
) -> None:
    """Read-modify-write under exclusive lock (separate lock file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".rwlock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            rows = load_roster(path) if path.exists() else []
            new_rows = mutator(rows)
            for r in new_rows:
                validate_roster_row(r)
            save_roster_atomic(path, new_rows)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def find_student(rows: list[dict[str, str]], student_id: str) -> dict[str, str] | None:
    sid = student_id.strip()
    for r in rows:
        if r.get("学号", "").strip() == sid:
            return r
    return None


def validate_roster_row(row: dict[str, str]) -> None:
    if not row.get("学号", "").strip():
        raise ValueError("学号 is required")
    if not row.get("姓名", "").strip():
        raise ValueError("姓名 is required")


def unique_student_ids(rows: list[dict[str, str]]) -> bool:
    seen: set[str] = set()
    for r in rows:
        sid = r.get("学号", "").strip()
        if sid in seen:
            return False
        seen.add(sid)
    return True

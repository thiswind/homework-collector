"""Locked atomic read/write for course.yaml (no database)."""
from __future__ import annotations

import fcntl
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def validate_course_id(course_id: str) -> str:
    s = (course_id or "").strip()
    if not _ID_RE.match(s):
        raise ValueError(
            "course_id must be 1–80 chars: letters, digits, hyphen, underscore only"
        )
    return s


def validate_assignment_id(aid: str) -> str:
    s = (aid or "").strip()
    if not _ID_RE.match(s):
        raise ValueError(
            f"Invalid assignment id {s!r}: use letters, digits, hyphen, underscore (1–80)"
        )
    return s


def validate_and_build_course_dict(
    course_id: str,
    course_title: str,
    assignment_ids: list[str],
    assignment_titles: list[str],
) -> dict[str, Any]:
    cid = validate_course_id(course_id)
    title = (course_title or "").strip()
    if not title:
        raise ValueError("course_title is required")
    if len(assignment_ids) != len(assignment_titles):
        raise ValueError("assignment rows mismatch")
    if not assignment_ids:
        raise ValueError("At least one assignment is required")
    seen: set[str] = set()
    assignments: list[dict[str, Any]] = []
    for order, (raw_id, raw_title) in enumerate(
        zip(assignment_ids, assignment_titles, strict=True), start=1
    ):
        aid = validate_assignment_id(raw_id)
        t = (raw_title or "").strip()
        if not t:
            raise ValueError(f"Assignment {aid}: title is required")
        if aid in seen:
            raise ValueError(f"Duplicate assignment id: {aid}")
        seen.add(aid)
        assignments.append({"id": aid, "title": t, "order": order})
    return {"course_id": cid, "course_title": title, "assignments": assignments}


def save_course_config_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write YAML under exclusive lock; optional .bak before replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".rwlock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    with open(lock_path, "a+", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            if path.exists() and path.stat().st_size > 0:
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                bak = path.parent / f"{path.name}.bak.{ts}"
                bak.write_bytes(path.read_bytes())
            fd, tmp = tempfile.mkstemp(
                prefix="course_", suffix=".yaml", dir=str(path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)

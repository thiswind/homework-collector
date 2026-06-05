from __future__ import annotations

import fcntl
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_COURSE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_course_id(course_id: str) -> str:
    s = (course_id or "").strip()
    if not _COURSE_ID_RE.match(s):
        raise ValueError("course id must be 1–80 chars: letters, digits, hyphen, underscore only")
    return s


def registry_path(data_dir: Path) -> Path:
    return data_dir / "courses.yaml"


def courses_root(data_dir: Path) -> Path:
    return data_dir / "courses"


def course_dir(data_dir: Path, course_id: str) -> Path:
    cid = validate_course_id(course_id)
    return courses_root(data_dir) / cid


def course_config_path(data_dir: Path, course_id: str) -> Path:
    return course_dir(data_dir, course_id) / "course.yaml"


def course_roster_path(data_dir: Path, course_id: str) -> Path:
    return course_dir(data_dir, course_id) / "roster.csv"


def course_storage_root(data_dir: Path, course_id: str) -> Path:
    return course_dir(data_dir, course_id) / "storage"


def course_templates_root(data_dir: Path, course_id: str) -> Path:
    return course_dir(data_dir, course_id) / "templates"


def normalize_registry(data: Any) -> dict[str, list[dict[str, str]]]:
    if not isinstance(data, dict):
        return {"courses": []}
    courses = data.get("courses")
    if not isinstance(courses, list):
        courses = []
    normalized: list[dict[str, str]] = []
    for item in courses:
        if not isinstance(item, dict):
            continue
        cid = validate_course_id(str(item.get("id", "")))
        title = str(item.get("title", "")).strip() or cid
        status = str(item.get("status", "active")).strip() or "active"
        if status not in {"active", "archived"}:
            status = "active"
        normalized.append(
            {
                "id": cid,
                "title": title,
                "status": status,
                "created_at": str(item.get("created_at", "")),
                "updated_at": str(item.get("updated_at", "")),
            }
        )
    return {"courses": normalized}


def load_course_registry(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    path = registry_path(data_dir)
    if not path.exists() or path.stat().st_size == 0:
        return {"courses": []}
    return normalize_registry(yaml.safe_load(path.read_text(encoding="utf-8")))


def save_course_registry_atomic(data_dir: Path, data: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = registry_path(data_dir)
    lock_path = path.with_suffix(path.suffix + ".rwlock")
    text = yaml.safe_dump(normalize_registry(data), allow_unicode=True, sort_keys=False)
    with open(lock_path, "a+", encoding="utf-8") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            fd, tmp = tempfile.mkstemp(prefix="courses_", suffix=".yaml", dir=str(data_dir))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def ensure_course_registry(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    root = courses_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    data = load_course_registry(data_dir)
    if not registry_path(data_dir).exists():
        save_course_registry_atomic(data_dir, data)
    return data


def find_course(data_dir: Path, course_id: str) -> dict[str, str] | None:
    cid = validate_course_id(course_id)
    for course in load_course_registry(data_dir).get("courses", []):
        if course.get("id") == cid:
            return course
    return None


def create_course(data_dir: Path, course_id: str, title: str) -> dict[str, str]:
    cid = validate_course_id(course_id)
    t = (title or "").strip()
    if not t:
        raise ValueError("course title is required")
    data = ensure_course_registry(data_dir)
    if any(c.get("id") == cid for c in data.get("courses", [])):
        raise ValueError("course id already exists")
    now = utc_now_iso()
    course = {"id": cid, "title": t, "status": "active", "created_at": now, "updated_at": now}
    data["courses"].append(course)
    course_dir(data_dir, cid).mkdir(parents=True, exist_ok=True)
    course_storage_root(data_dir, cid).mkdir(parents=True, exist_ok=True)
    course_templates_root(data_dir, cid).mkdir(parents=True, exist_ok=True)
    save_course_registry_atomic(data_dir, data)
    return course

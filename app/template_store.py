from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

from app.course_store import validate_assignment_id

_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip"}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_template_filename(filename: str) -> str:
    raw = Path(filename or "").name.strip()
    if not raw:
        raise ValueError("template filename is required")
    suffix = Path(raw).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError("unsupported template file type")
    secured = secure_filename(raw)
    if not secured or Path(secured).suffix.lower() != suffix:
        stem = _SAFE_NAME_RE.sub("_", Path(raw).stem).strip("._") or "template"
        secured = stem + suffix
    if "/" in secured or "\\" in secured or secured in {".", ".."}:
        raise ValueError("invalid template filename")
    return secured


def validate_template_bytes(data: bytes, max_bytes: int) -> None:
    if not data:
        raise ValueError("template file is empty")
    if len(data) > max_bytes:
        raise ValueError("template file is too large")


def assignment_template_dir(templates_root: Path, assignment_id: str) -> Path:
    aid = validate_assignment_id(assignment_id)
    return templates_root / aid


def store_assignment_template(
    templates_root: Path,
    assignment_id: str,
    original_name: str,
    data: bytes,
    max_bytes: int,
) -> dict[str, Any]:
    filename = validate_template_filename(original_name)
    validate_template_bytes(data, max_bytes)
    target_dir = assignment_template_dir(templates_root, assignment_id)
    if target_dir.exists():
        for item in target_dir.iterdir():
            if item.is_file():
                item.unlink()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_bytes(data)
    return {"filename": filename, "original_name": Path(original_name).name, "uploaded_at": utc_now_iso()}


def remove_assignment_template(templates_root: Path, assignment_id: str) -> None:
    target_dir = assignment_template_dir(templates_root, assignment_id)
    if not target_dir.exists():
        return
    for item in target_dir.iterdir():
        if item.is_file():
            item.unlink()


def template_path(templates_root: Path, assignment_id: str, metadata: dict[str, Any] | None) -> Path | None:
    if not metadata or not metadata.get("filename"):
        return None
    filename = validate_template_filename(str(metadata["filename"]))
    path = assignment_template_dir(templates_root, assignment_id) / filename
    return path if path.exists() else None

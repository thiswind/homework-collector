from pathlib import Path
from typing import Any

import yaml


def load_course_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not data or "course_id" not in data:
        raise ValueError("course.yaml must define course_id")
    if "assignments" not in data:
        data["assignments"] = []
    return data


def ensure_assignment_dirs(storage_root: Path, assignments: list[dict[str, Any]]) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    for a in assignments:
        aid = a.get("id")
        if aid:
            (storage_root / str(aid)).mkdir(parents=True, exist_ok=True)

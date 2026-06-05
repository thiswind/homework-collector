from __future__ import annotations

import csv
import shutil
from pathlib import Path

from app.course_loader import ensure_assignment_dirs, load_course_config
from app.course_registry import (
    course_config_path,
    course_roster_path,
    course_storage_root,
    create_course,
    ensure_course_registry,
)
from app.roster_store import save_roster_atomic, strip_bom


def ensure_course_config(project_root: Path, course_config_path: Path) -> None:
    if course_config_path.exists() and course_config_path.stat().st_size > 0:
        return
    bundled = project_root / "config" / "course.yaml"
    course_config_path.parent.mkdir(parents=True, exist_ok=True)
    if bundled.exists():
        shutil.copyfile(bundled, course_config_path)
    else:
        course_config_path.write_text(
            "course_id: default-course\ncourse_title: Course\nassignments: []\n",
            encoding="utf-8",
        )


def _norm_header(k: str | None) -> str:
    s = strip_bom((k or "").strip())
    if s == "":
        return "序号"
    return s


def migrate_roster_from_seed(project_root: Path, roster_path: Path) -> None:
    if roster_path.exists() and roster_path.stat().st_size > 0:
        return
    seed = project_root / "点名册.csv"
    if not seed.exists():
        roster_path.parent.mkdir(parents=True, exist_ok=True)
        save_roster_atomic(roster_path, [])
        return
    raw = seed.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(raw.splitlines())
    rows_out: list[dict[str, str]] = []
    for i, row in enumerate(reader, start=1):
        norm: dict[str, str] = {}
        for k, v in row.items():
            norm[_norm_header(k)] = (v or "").strip()
        seq = norm.get("序号") or norm.get("") or str(i)
        rows_out.append(
            {
                "序号": str(seq),
                "学院": norm.get("学院", ""),
                "专业": norm.get("专业", ""),
                "学号": norm.get("学号", ""),
                "姓名": norm.get("姓名", ""),
                "密码哈希": "",
            }
        )
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    save_roster_atomic(roster_path, rows_out)


def bootstrap_storage(course_config: Path, storage_root: Path) -> dict:
    cfg = load_course_config(course_config)
    ensure_assignment_dirs(storage_root, cfg.get("assignments", []))
    return cfg


def bootstrap_courses(project_root: Path, data_dir: Path) -> dict:
    registry = ensure_course_registry(data_dir)
    if not registry.get("courses"):
        bundled = project_root / "config" / "course.yaml"
        if bundled.exists():
            seeded = load_course_config(bundled)
            cid = str(seeded.get("course_id", "default-course"))
            title = str(seeded.get("course_title", cid))
        else:
            cid = "default-course"
            title = "Course"
        create_course(data_dir, cid, title)
        cfg_path = course_config_path(data_dir, cid)
        ensure_course_config(project_root, cfg_path)
        if bundled.exists():
            data = load_course_config(cfg_path)
            data["course_id"] = cid
            data["course_title"] = title
            from app.course_store import save_course_config_atomic

            save_course_config_atomic(cfg_path, data)
        migrate_roster_from_seed(project_root, course_roster_path(data_dir, cid))
        bootstrap_storage(cfg_path, course_storage_root(data_dir, cid))
        registry = ensure_course_registry(data_dir)
    for course in registry.get("courses", []):
        cid = course["id"]
        cfg_path = course_config_path(data_dir, cid)
        ensure_course_config(project_root, cfg_path)
        migrate_roster_from_seed(project_root, course_roster_path(data_dir, cid))
        bootstrap_storage(cfg_path, course_storage_root(data_dir, cid))
    return registry

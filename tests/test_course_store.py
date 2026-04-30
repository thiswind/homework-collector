"""PLAN-B-002 Phase A: course_store validation and atomic save."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.course_loader import load_course_config
from app.course_store import (
    save_course_config_atomic,
    validate_and_build_course_dict,
    validate_assignment_id,
)


def test_validate_and_build_ok():
    d = validate_and_build_course_dict(
        "c-101",
        "Intro",
        ["hw01", "hw02"],
        ["First", "Second"],
    )
    assert d["course_id"] == "c-101"
    assert d["course_title"] == "Intro"
    assert len(d["assignments"]) == 2
    assert d["assignments"][0]["order"] == 1
    assert d["assignments"][1]["order"] == 2


def test_rejects_bad_id():
    with pytest.raises(ValueError):
        validate_assignment_id("../x")


def test_rejects_duplicate_assignment_ids():
    with pytest.raises(ValueError):
        validate_and_build_course_dict("c", "T", ["a", "a"], ["1", "2"])


def test_roundtrip_yaml(tmp_path: Path):
    p = tmp_path / "course.yaml"
    data = validate_and_build_course_dict("cid", "Title", ["x1"], ["One"])
    save_course_config_atomic(p, data)
    loaded = load_course_config(p)
    assert loaded["course_id"] == "cid"
    assert loaded["assignments"][0]["id"] == "x1"

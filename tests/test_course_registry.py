from __future__ import annotations

import pytest

from app.course_registry import (
    course_config_path,
    course_roster_path,
    course_storage_root,
    course_templates_root,
    create_course,
    ensure_course_registry,
    find_course,
    load_course_registry,
    validate_course_id,
)


def test_validate_course_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        validate_course_id("../x")


def test_create_course_writes_registry_and_dirs(tmp_path):
    ensure_course_registry(tmp_path)
    course = create_course(tmp_path, "c-101", "Course 101")
    assert course["id"] == "c-101"
    assert find_course(tmp_path, "c-101")["title"] == "Course 101"
    assert load_course_registry(tmp_path)["courses"][0]["id"] == "c-101"
    assert course_config_path(tmp_path, "c-101").parent.exists()
    assert course_roster_path(tmp_path, "c-101").parent.exists()
    assert course_storage_root(tmp_path, "c-101").exists()
    assert course_templates_root(tmp_path, "c-101").exists()


def test_create_course_rejects_duplicate(tmp_path):
    create_course(tmp_path, "c", "Course")
    with pytest.raises(ValueError):
        create_course(tmp_path, "c", "Course Again")

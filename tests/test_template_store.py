from __future__ import annotations

import pytest

from app.template_store import (
    remove_assignment_template,
    store_assignment_template,
    template_path,
    validate_template_filename,
)


def test_validate_template_filename_rejects_unsupported_type():
    with pytest.raises(ValueError):
        validate_template_filename("x.exe")


def test_store_template_replaces_existing(tmp_path):
    meta1 = store_assignment_template(tmp_path, "hw01", "第一次.docx", b"abc", 1024)
    p1 = template_path(tmp_path, "hw01", meta1)
    assert p1 is not None
    assert p1.read_bytes() == b"abc"

    meta2 = store_assignment_template(tmp_path, "hw01", "second.pdf", b"pdf", 1024)
    p2 = template_path(tmp_path, "hw01", meta2)
    assert p2 is not None
    assert p2.name == "second.pdf"
    assert p2.read_bytes() == b"pdf"
    assert not p1.exists()


def test_remove_template(tmp_path):
    meta = store_assignment_template(tmp_path, "hw01", "template.zip", b"abc", 1024)
    remove_assignment_template(tmp_path, "hw01")
    assert template_path(tmp_path, "hw01", meta) is None


def test_store_template_rejects_too_large(tmp_path):
    with pytest.raises(ValueError):
        store_assignment_template(tmp_path, "hw01", "template.pdf", b"abc", 2)

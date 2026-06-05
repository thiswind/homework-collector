"""Teacher course management auth and save."""
from __future__ import annotations

from app.course_loader import load_course_config
from app.course_registry import course_config_path


def test_anonymous_redirects_course(client):
    r = client.get("/teacher/course", follow_redirects=False)
    assert r.status_code == 302
    assert "/teacher/login" in r.headers.get("Location", "")


def test_student_cannot_open_course(client):
    with client.session_transaction() as sess:
        sess["student_id"] = "2023001"
    r = client.get("/teacher/course", follow_redirects=False)
    assert r.status_code == 302


def test_teacher_save_updates_course_file(client, app, default_course_id):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    cfg = app.extensions["cfg"]
    path = course_config_path(cfg.DATA_DIR, default_course_id)
    r = client.post(
        f"/teacher/courses/{default_course_id}/settings",
        data={
            "csrf_token": "dummy",
            "course_id": default_course_id,
            "course_title": "Edited Title",
            "assignment_id": ["ea1"],
            "assignment_title": ["Essay A"],
            "submit": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    data = load_course_config(path)
    assert data["course_id"] == default_course_id
    assert data["course_title"] == "Edited Title"
    assert data["assignments"][0]["id"] == "ea1"

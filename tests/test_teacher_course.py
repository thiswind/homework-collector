"""PLAN-B-002 Phases B/C: teacher course editor auth and save."""
from __future__ import annotations

from app.course_loader import load_course_config


def test_anonymous_redirects_course(client):
    r = client.get("/teacher/course", follow_redirects=False)
    assert r.status_code == 302
    assert "/teacher/login" in r.headers.get("Location", "")


def test_student_cannot_open_course(client):
    with client.session_transaction() as sess:
        sess["student_id"] = "2023001"
    r = client.get("/teacher/course", follow_redirects=False)
    assert r.status_code == 302


def test_teacher_save_updates_file_and_extension(client, app):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    cfg = app.extensions["cfg"]
    path = cfg.COURSE_CONFIG
    r = client.post(
        "/teacher/course",
        data={
            "csrf_token": "dummy",
            "course_id": "edited-course",
            "course_title": "Edited Title",
            "assignment_id": ["ea1"],
            "assignment_title": ["Essay A"],
            "submit": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    data = load_course_config(path)
    assert data["course_id"] == "edited-course"
    assert data["course_title"] == "Edited Title"
    assert data["assignments"][0]["id"] == "ea1"
    assert app.extensions["course_cfg"]["course_id"] == "edited-course"

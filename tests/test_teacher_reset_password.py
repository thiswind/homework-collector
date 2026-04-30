"""Teacher reset student password: roster hash updates."""
from __future__ import annotations

import re

from werkzeug.security import check_password_hash

from app.roster_store import find_student, load_roster


def test_teacher_reset_password_updates_hash(client, app):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    cfg = app.extensions["cfg"]
    sid = "12024215112"
    rows_before = load_roster(cfg.ROSTER_PATH)
    row = find_student(rows_before, sid)
    assert row is not None
    old_hash = (row.get("密码哈希") or "").strip()

    resp = client.post(
        f"/teacher/roster/reset-password/{sid}",
        data={"csrf_token": "dummy", "submit": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "teacher-reset-plain" in html
    m = re.search(r'id="teacher-reset-plain"[^>]*>([^<]+)<', html)
    assert m, "plain password block present"
    plain = m.group(1).strip()
    assert len(plain) >= 8

    rows_after = load_roster(cfg.ROSTER_PATH)
    row2 = find_student(rows_after, sid)
    new_hash = (row2.get("密码哈希") or "").strip()
    assert new_hash
    assert new_hash != old_hash
    assert check_password_hash(new_hash, plain)


def test_teacher_reset_unknown_student_redirects(client, app):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    resp = client.post(
        "/teacher/roster/reset-password/nosuch999",
        data={"csrf_token": "dummy", "submit": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "名册中无此学号" in resp.get_data(as_text=True)


def test_anonymous_cannot_reset_password(client):
    r = client.post(
        "/teacher/roster/reset-password/12024215112",
        data={"submit": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 302

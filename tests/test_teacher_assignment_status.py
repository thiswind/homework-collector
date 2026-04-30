"""Teacher assignment submission status page vs roster + manifest."""
from __future__ import annotations

import re

from app.manifest_store import load_manifest, manifest_path_for, update_manifest
from app.roster_store import load_roster


def test_anonymous_cannot_view_assignment_status(client):
    r = client.get("/teacher/assignments/hw01/status", follow_redirects=False)
    assert r.status_code == 302
    assert "/teacher/login" in r.headers.get("Location", "")


def test_teacher_status_page_matches_manifest(client, app):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    cfg = app.extensions["cfg"]
    aid = "hw01"
    mp = manifest_path_for(cfg.STORAGE_ROOT, aid)
    submitted_sid = "12024215112"
    other_sid = "12024215142"
    update_manifest(mp, submitted_sid, "demo_hw01.pdf", replace=True)
    man = load_manifest(mp)
    assert man[submitted_sid]["filename"] == "demo_hw01.pdf"
    assert other_sid not in man or not (man.get(other_sid) or {}).get("filename")

    rows = load_roster(cfg.ROSTER_PATH)
    assert any((r.get("学号") or "").strip() == submitted_sid for r in rows)
    assert any((r.get("学号") or "").strip() == other_sid for r in rows)

    resp = client.get(f"/teacher/assignments/{aid}/status")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "overflow-x-auto" in html

    def status_for_sid(sid: str) -> str:
        m = re.search(
            rf'data-student-id="{re.escape(sid)}"[^>]*>.*?data-testid="(status-submitted|status-missing)"',
            html,
            re.DOTALL,
        )
        assert m, f"row for {sid} with status marker"
        return m.group(1)

    assert status_for_sid(submitted_sid) == "status-submitted"
    assert status_for_sid(other_sid) == "status-missing"

    m_row = re.search(
        rf'data-student-id="{re.escape(submitted_sid)}"[^>]*data-last-updated="([^"]*)"',
        html,
    )
    assert m_row
    assert m_row.group(1) == man[submitted_sid]["last_updated_at"]

    m_other = re.search(
        rf'data-student-id="{re.escape(other_sid)}"[^>]*data-last-updated="([^"]*)"',
        html,
    )
    assert m_other
    assert m_other.group(1) == ""


def test_roster_page_links_to_submission_status(client, app):
    with client.session_transaction() as sess:
        sess["teacher"] = True
    r = client.get("/teacher/roster")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "/teacher/assignments/hw01/status" in text
    assert "提交进度" in text

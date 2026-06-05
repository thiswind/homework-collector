from pathlib import Path

import pytest

from app import create_app
from app.config import Config
from app.course_registry import course_config_path, course_roster_path, course_storage_root


DEFAULT_COURSE_ID = "MTECH-2026-SPRING"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(Config, "DATA_DIR", d)
    monkeypatch.setattr(Config, "COURSES_REGISTRY", d / "courses.yaml")
    monkeypatch.setattr(Config, "COURSES_ROOT", d / "courses")
    monkeypatch.setattr(Config, "ROSTER_PATH", course_roster_path(d, DEFAULT_COURSE_ID))
    monkeypatch.setattr(Config, "STORAGE_ROOT", course_storage_root(d, DEFAULT_COURSE_ID))
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret-key-for-pytest")
    monkeypatch.setattr(Config, "TEACHER_USERNAME", "teacher")
    monkeypatch.setattr(Config, "TEACHER_PASSWORD", "teacherpw")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "COURSE_CONFIG", course_config_path(d, DEFAULT_COURSE_ID))
    application = create_app(Config)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def default_course_id():
    return DEFAULT_COURSE_ID

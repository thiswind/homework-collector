from pathlib import Path

import pytest

from app import create_app
from app.config import Config


@pytest.fixture()
def app(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(Config, "DATA_DIR", d)
    monkeypatch.setattr(Config, "ROSTER_PATH", d / "roster.csv")
    monkeypatch.setattr(Config, "STORAGE_ROOT", d / "storage")
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret-key-for-pytest")
    monkeypatch.setattr(Config, "TEACHER_USERNAME", "teacher")
    monkeypatch.setattr(Config, "TEACHER_PASSWORD", "teacherpw")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "COURSE_CONFIG", d / "course.yaml")
    application = create_app(Config)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()

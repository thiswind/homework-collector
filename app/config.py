import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
    ROSTER_PATH = Path(os.environ.get("ROSTER_PATH", str(DATA_DIR / "roster.csv")))
    STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", str(DATA_DIR / "storage")))
    # Runtime course file on persistent disk (Fly: /data/course.yaml). Override for dev.
    COURSE_CONFIG = Path(
        os.environ.get("COURSE_CONFIG", str(DATA_DIR / "course.yaml"))
    )
    TEACHER_USERNAME = os.environ.get("TEACHER_USERNAME", "teacher")
    TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD", "")
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
    DISPLAY_TZ = os.environ.get("DISPLAY_TZ", "Asia/Shanghai")
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("PERMANENT_SESSION_LIFETIME", str(8 * 3600)))
    WTF_CSRF_ENABLED = _bool("WTF_CSRF_ENABLED", True)
    WTF_CSRF_TIME_LIMIT = None


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False

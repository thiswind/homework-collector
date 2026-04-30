import os
from datetime import timedelta

from flask import Flask, current_app
from flask_wtf.csrf import CSRFProtect

from app.bootstrap import bootstrap_storage, ensure_course_config, migrate_roster_from_seed
from app.config import Config
from app.site import register_blueprints

csrf = CSRFProtect()


def create_app(config_class: type[Config] | None = None):
    config_class = config_class or Config
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config.from_object(config_class)
    app.config.setdefault("WTF_CSRF_ENABLED", config_class.WTF_CSRF_ENABLED)

    app.extensions["cfg"] = config_class
    migrate_roster_from_seed(config_class.PROJECT_ROOT, config_class.ROSTER_PATH)
    ensure_course_config(config_class.PROJECT_ROOT, config_class.COURSE_CONFIG)
    course_cfg = bootstrap_storage(config_class.COURSE_CONFIG, config_class.STORAGE_ROOT)
    app.extensions["course_cfg"] = course_cfg

    app.permanent_session_lifetime = timedelta(seconds=config_class.PERMANENT_SESSION_LIFETIME)

    csrf.init_app(app)

    register_blueprints(app)

    if os.environ.get("FLASK_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.context_processor
    def inject_course():
        cfg = current_app.extensions.get("course_cfg") or {}
        return {"course_title": cfg.get("course_title", "")}

    return app

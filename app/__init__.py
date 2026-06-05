from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from app.bootstrap import bootstrap_courses
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
    app.extensions["course_registry"] = bootstrap_courses(config_class.PROJECT_ROOT, config_class.DATA_DIR)
    app.permanent_session_lifetime = timedelta(seconds=config_class.PERMANENT_SESSION_LIFETIME)

    csrf.init_app(app)
    register_blueprints(app)

    if os.environ.get("FLASK_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.context_processor
    def inject_globals():
        return {"course_title": "作业提交系统"}

    return app

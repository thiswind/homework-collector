#!/usr/bin/env python3
"""WSGI entry for gunicorn."""
from app import create_app

application = create_app()

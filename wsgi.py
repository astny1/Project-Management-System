"""Production entrypoint for Gunicorn (Render, etc.)."""
from reset_db import bootstrap_production

bootstrap_production()

from app import app  # noqa: E402,F401

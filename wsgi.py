"""Production entrypoint for Gunicorn (Render, etc.)."""
from database import init_db, migrate_db
from seed import seed

init_db()
migrate_db()
seed()

from app import app  # noqa: E402,F401

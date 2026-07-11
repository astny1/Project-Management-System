"""Production entrypoint for Gunicorn (Render, etc.)."""
import os

from reset_db import bootstrap_production

bootstrap_production()

from app import app  # noqa: E402,F401

if os.environ.get("ENABLE_WEEKLY_DIGEST") == "1":
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from database import get_db
        from weekly_digest import send_weekly_digest

        def _job():
            with get_db() as conn:
                send_weekly_digest(conn)

        scheduler = BackgroundScheduler()
        scheduler.add_job(_job, "cron", day_of_week="mon", hour=8, minute=0)
        scheduler.start()
    except Exception as exc:
        print(f"[Weekly digest scheduler] {exc}")

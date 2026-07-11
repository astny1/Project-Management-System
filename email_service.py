"""Email notifications — sends to info@growhivemedea.com (configure SMTP on Render)."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from company_defaults import DEFAULT_COMPANY_NAME, DEFAULT_EMAIL

NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", DEFAULT_EMAIL)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or NOTIFY_EMAIL)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(subject: str, html_body: str, text_body: str | None = None, to_email: str | None = None) -> bool:
    recipient = to_email or NOTIFY_EMAIL
    text_body = text_body or html_body.replace("<br>", "\n").replace("<br/>", "\n")

    if not smtp_configured():
        print(f"[EMAIL not configured] To: {recipient} | Subject: {subject}")
        print(text_body[:500])
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{DEFAULT_COMPANY_NAME} — {subject}"
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [recipient], msg.as_string())
        return True
    except Exception as exc:
        print(f"[EMAIL error] {exc}")
        return False


def log_and_send(conn, subject: str, html_body: str, notification_type: str = "general") -> bool:
    ok = send_email(subject, html_body)
    try:
        conn.execute(
            """
            INSERT INTO email_notifications (notification_type, recipient, subject, body_preview, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (notification_type, NOTIFY_EMAIL, subject, html_body[:500], "sent" if ok else "failed"),
        )
    except Exception:
        pass
    return ok


def notify_simple(conn, subject: str, lines: list[str], notification_type: str = "alert") -> bool:
    html = "<br>".join(lines)
    html = f"<div style='font-family:sans-serif;font-size:14px;'>{html}</div>"
    return log_and_send(conn, subject, html, notification_type)

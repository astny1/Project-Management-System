"""Fresh database setup — local reset and Render production seeding."""
from __future__ import annotations

import os
import sys

from werkzeug.security import generate_password_hash

from company_defaults import DEFAULT_ADDRESS, DEFAULT_EMAIL, DEFAULT_PHONE, DEFAULT_TAGLINE

from database import DB_PATH, get_db, init_db, migrate_db


def wipe_database() -> bool:
    """Delete the database file. Returns True if a file was removed."""
    if DB_PATH.exists():
        os.remove(DB_PATH)
        return True
    return False


def _insert_fresh_defaults(conn, include_team: bool = False) -> None:
    conn.execute(
        """
        INSERT INTO users (email, password_hash, name, role)
        VALUES (?, ?, ?, ?)
        """,
        (
            "astone.mwamba@growhivemedea.com",
            generate_password_hash("admin123"),
            "Admin Director",
            "admin",
        ),
    )

    if include_team:
        conn.executemany(
            """
            INSERT INTO users (email, password_hash, name, role)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("sales@growthhivemedia.com", generate_password_hash("sales123"), "Sales Manager", "sales_manager"),
                ("pm@growthhivemedia.com", generate_password_hash("pm123"), "Project Manager", "project_manager"),
            ],
        )

    conn.execute(
        """
        INSERT INTO company_settings
        (id, company_name, tagline, email, phone, address, bank_balance,
         monthly_profit_target, yearly_investment_goal)
        VALUES (1, ?, ?, ?, ?, ?, 0, 0, 0)
        """,
        (
            "GrowthHive Media",
            DEFAULT_TAGLINE,
            DEFAULT_EMAIL,
            DEFAULT_PHONE,
            DEFAULT_ADDRESS,
        ),
    )

    conn.execute(
        """
        INSERT INTO bank_accounts (bank_name, account_label, account_number, balance, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Stanbic Bank Zambia",
            "GrowthHive Media — Main Account",
            "",
            0.0,
            "Primary company operating account",
        ),
    )


def ensure_single_stanbic_bank(conn, balance: float = 0.0) -> None:
    """One Stanbic account; sync company_settings bank_balance."""
    conn.execute("DELETE FROM bank_accounts")
    conn.execute(
        """
        INSERT INTO bank_accounts (bank_name, account_label, account_number, balance, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Stanbic Bank Zambia",
            "GrowthHive Media — Main Account",
            "",
            balance,
            "Primary company operating account",
        ),
    )
    conn.execute("UPDATE company_settings SET bank_balance = ? WHERE id = 1", (balance,))


def seed_fresh_if_empty(include_team: bool = False) -> None:
    """Create empty production database on first run only (no demo projects)."""
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]:
            return
        conn.execute("DELETE FROM bank_accounts")
        _insert_fresh_defaults(conn, include_team=include_team)
        ensure_single_stanbic_bank(conn, 0.0)


def reset_fresh(include_team: bool = False) -> None:
    """Delete local database and recreate empty (for development)."""
    if wipe_database():
        print(f"Deleted {DB_PATH}")
    init_db()
    migrate_db()
    with get_db() as conn:
        conn.execute("DELETE FROM bank_accounts")
        _insert_fresh_defaults(conn, include_team=include_team)
        ensure_single_stanbic_bank(conn, 0.0)
    print("Fresh database ready — no demo projects, clients, or finances.")
    print("Login: astone.mwamba@growhivemedea.com / admin123")
    print("Change your password in Settings after logging in.")


def bootstrap_production() -> None:
    """Used by wsgi.py on Render — optional one-time wipe via RESET_DATABASE=1."""
    include_team = os.environ.get("INCLUDE_TEAM") == "1"
    reset = os.environ.get("RESET_DATABASE") == "1"
    if reset:
        wipe_database()
    init_db()
    migrate_db()
    seed_fresh_if_empty(include_team=include_team)
    if reset:
        with get_db() as conn:
            ensure_single_stanbic_bank(conn, 0.0)


if __name__ == "__main__":
    team = "--team" in sys.argv
    reset_fresh(include_team=team)

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DATABASE_PATH", Path(__file__).parent / "growthhive.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'sales_manager', 'project_manager'))
            );

            CREATE TABLE IF NOT EXISTS company_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                company_name TEXT NOT NULL,
                tagline TEXT,
                email TEXT,
                phone TEXT,
                address TEXT,
                bank_balance REAL NOT NULL DEFAULT 0,
                monthly_profit_target REAL NOT NULL DEFAULT 0,
                yearly_investment_goal REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                client_company TEXT NOT NULL,
                client_contact_name TEXT,
                client_email TEXT,
                client_phone TEXT,
                client_address TEXT,
                client_website TEXT,
                client_location TEXT,
                contract_amount REAL NOT NULL DEFAULT 0,
                payment_terms TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'ongoing', 'completed')),
                duration_weeks INTEGER NOT NULL DEFAULT 0,
                has_monthly_maintenance INTEGER NOT NULL DEFAULT 0,
                maintenance_amount REAL DEFAULT 0,
                start_date TEXT,
                end_date TEXT,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                category TEXT,
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS payments_received (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                payment_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS subcontractors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                company TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                contract_amount REAL NOT NULL DEFAULT 0,
                amount_paid REAL NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT NOT NULL,
                account_label TEXT,
                account_number TEXT,
                balance REAL NOT NULL DEFAULT 0,
                notes TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS company_reserves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                purpose TEXT,
                category TEXT,
                reserve_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS company_investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                business_type TEXT,
                amount REAL NOT NULL DEFAULT 0,
                expected_return REAL DEFAULT 0,
                actual_return REAL DEFAULT 0,
                investment_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS investment_profits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                profit_date TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (investment_id) REFERENCES company_investments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS monthly_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                revenue_target REAL NOT NULL DEFAULT 0,
                profit_target REAL NOT NULL DEFAULT 0,
                investment_target REAL NOT NULL DEFAULT 0,
                UNIQUE(year, month)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requested_by INTEGER NOT NULL,
                requested_by_name TEXT,
                action_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                payload TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_by_name TEXT,
                review_note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at TEXT,
                FOREIGN KEY (requested_by) REFERENCES users(id)
            );
            """
        )
        migrate_db(conn)


def migrate_db(conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        if not _column_exists(conn, "projects", "client_website"):
            conn.execute("ALTER TABLE projects ADD COLUMN client_website TEXT")
        if not _column_exists(conn, "projects", "client_location"):
            conn.execute("ALTER TABLE projects ADD COLUMN client_location TEXT")
        if not _column_exists(conn, "company_settings", "monthly_profit_target"):
            conn.execute("ALTER TABLE company_settings ADD COLUMN monthly_profit_target REAL NOT NULL DEFAULT 0")
        if not _column_exists(conn, "company_settings", "yearly_investment_goal"):
            conn.execute("ALTER TABLE company_settings ADD COLUMN yearly_investment_goal REAL NOT NULL DEFAULT 0")

        # Allow company-wide expenses (nullable project_id)
        exp_info = conn.execute("PRAGMA table_info(expenses)").fetchall()
        project_col = next((c for c in exp_info if c[1] == "project_id"), None)
        if project_col and project_col[3] == 1:  # NOT NULL
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS expenses_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT,
                    expense_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                INSERT INTO expenses_new SELECT * FROM expenses;
                DROP TABLE expenses;
                ALTER TABLE expenses_new RENAME TO expenses;
                """
            )

        if not _column_exists(conn, "company_investments", "business_type"):
            conn.execute("ALTER TABLE company_investments ADD COLUMN business_type TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS investment_profits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                profit_date TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (investment_id) REFERENCES company_investments(id) ON DELETE CASCADE
            )
            """
        )

        _migrate_single_stanbic_bank(conn)
        _migrate_user_roles(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requested_by INTEGER NOT NULL,
                requested_by_name TEXT,
                action_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                payload TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_by_name TEXT,
                review_note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at TEXT,
                FOREIGN KEY (requested_by) REFERENCES users(id)
            )
            """
        )

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def _migrate_single_stanbic_bank(conn):
    """Keep only one main account — Stanbic Bank Zambia."""
    rows = conn.execute("SELECT COUNT(*) AS c FROM bank_accounts").fetchone()["c"]
    if rows == 1:
        only = conn.execute("SELECT bank_name FROM bank_accounts LIMIT 1").fetchone()
        if only and "Stanbic" in only["bank_name"]:
            return
    total = conn.execute("SELECT COALESCE(SUM(balance), 0) AS t FROM bank_accounts").fetchone()["t"]
    if total == 0:
        company = conn.execute("SELECT bank_balance FROM company_settings WHERE id = 1").fetchone()
        total = float(company["bank_balance"]) if company else 0.0
    conn.execute("DELETE FROM bank_accounts")
    conn.execute(
        """
        INSERT INTO bank_accounts (bank_name, account_label, account_number, balance, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Stanbic Bank Zambia",
            "GrowthHive Media — Main Account",
            "9130009876543",
            total,
            "Primary company operating account",
        ),
    )
    conn.execute("UPDATE company_settings SET bank_balance = ? WHERE id = 1", (total,))


def _migrate_user_roles(conn):
    """Allow sales_manager role in users table."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not row or not row["sql"]:
        return
    if "sales_manager" in row["sql"]:
        return
    conn.executescript(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'project_manager'
        );
        INSERT INTO users_new (id, email, password_hash, name, role) SELECT id, email, password_hash, name, role FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
        """
    )

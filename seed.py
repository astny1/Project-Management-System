from werkzeug.security import generate_password_hash

from database import get_db, init_db, migrate_db


def seed_financials(conn):
    if conn.execute("SELECT COUNT(*) AS c FROM bank_accounts").fetchone()["c"]:
        return

    conn.execute(
        """
        INSERT INTO bank_accounts (bank_name, account_label, account_number, balance, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Stanbic Bank Zambia",
            "GrowthHive Media — Main Account",
            "9130009876543",
            780000.0,
            "Primary company operating account",
        ),
    )

    conn.executemany(
        """
        INSERT INTO company_reserves (name, amount, purpose, category, reserve_date, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("Emergency Operating Fund", 350000.0, "3-month runway protection", "Emergency", "2026-01-01", "Core economic buffer"),
            ("Equipment & Infrastructure", 180000.0, "Hardware, servers, office tech", "Infrastructure", "2026-01-15", "Strengthens delivery capacity"),
            ("Tax & Compliance Reserve", 95000.0, "ZRA obligations", "Compliance", "2026-02-01", "Quarterly tax planning"),
            ("Marketing Growth Fund", 125000.0, "Paid ads & brand campaigns", "Growth", "2026-03-01", "Company self-investment"),
        ],
    )

    conn.executemany(
        """
        INSERT INTO company_investments
        (name, business_type, amount, expected_return, actual_return, investment_date, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Digital Ad Platform Credits", "Marketing", 85000.0, 120000.0, 95000.0, "2026-01-20", "active", "Meta & Google ad spend"),
            ("Office Equipment Upgrade", "Infrastructure", 65000.0, 0, 0, "2026-02-10", "active", "Laptops and design workstations"),
            ("SaaS Tools Annual License", "Technology", 42000.0, 55000.0, 48000.0, "2026-03-05", "active", "Adobe, Figma, analytics stack"),
            ("ZedPay Fintech Stake", "Fintech", 150000.0, 200000.0, 75000.0, "2026-02-15", "active", "Minority stake in payment startup"),
        ],
    )

    for month in range(1, 13):
        conn.execute(
            """
            INSERT INTO monthly_targets (year, month, revenue_target, profit_target, investment_target)
            VALUES (2026, ?, ?, ?, ?)
            """,
            (month, 450000 + month * 25000, 180000 + month * 10000, 50000 + month * 5000),
        )

    conn.execute(
        """
        UPDATE company_settings SET
            bank_balance = ?,
            monthly_profit_target = ?,
            yearly_investment_goal = ?
        WHERE id = 1
        """,
        (780000.0, 250000.0, 600000.0),
    )

    # Backfill profit entries from existing investments if none yet
    if conn.execute("SELECT COUNT(*) AS c FROM investment_profits").fetchone()["c"] == 0:
        for inv in conn.execute("SELECT id, actual_return, investment_date, name FROM company_investments WHERE actual_return > 0").fetchall():
            conn.execute(
                """
                INSERT INTO investment_profits (investment_id, amount, profit_date, description)
                VALUES (?, ?, ?, ?)
                """,
                (inv["id"], inv["actual_return"], inv["investment_date"], f"Initial return — {inv['name']}"),
            )


def ensure_demo_users(conn):
    """Ensure all role accounts exist (for new installs and upgrades)."""
    new_admin = "astone.mwamba@growhivemedea.com"
    for old in ("admin@growthhivemedia.com",):
        row = conn.execute("SELECT id FROM users WHERE email = ?", (old,)).fetchone()
        if row and not conn.execute("SELECT id FROM users WHERE email = ?", (new_admin,)).fetchone():
            conn.execute(
                "UPDATE users SET email = ?, name = ? WHERE id = ?",
                (new_admin, "Admin Director", row["id"]),
            )

    demos = [
        (new_admin, "admin123", "Admin Director", "admin"),
        ("sales@growthhivemedia.com", "sales123", "Sales Manager", "sales_manager"),
        ("pm@growthhivemedia.com", "pm123", "Project Manager", "project_manager"),
    ]
    for email, password, name, role in demos:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)",
                (email, generate_password_hash(password), name, role),
            )


def seed():
    init_db()
    migrate_db()
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if not existing:
            ensure_demo_users(conn)

            conn.execute(
                """
                INSERT INTO company_settings
                (id, company_name, tagline, email, phone, address, bank_balance,
                 monthly_profit_target, yearly_investment_goal)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "GrowthHive Media",
                    "Technology & Marketing Solutions",
                    "info@growthhivemedia.com",
                    "+260 971 000 000",
                    "Plot 42, Cairo Road, Lusaka, Zambia",
                    2450000.0,
                    250000.0,
                    600000.0,
                ),
            )

            conn.execute(
                """
                INSERT INTO projects (
                    name, client_company, client_contact_name, client_email, client_phone,
                    client_address, client_website, client_location, contract_amount, payment_terms,
                    status, duration_weeks, has_monthly_maintenance, maintenance_amount,
                    start_date, end_date, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "E-Commerce Platform Redesign",
                    "ZamRetail Ltd",
                    "Sarah Mwamba",
                    "sarah@zamretail.com",
                    "+260 971 234 567",
                    "Shop 12, East Park Mall, Lusaka",
                    "https://www.zamretail.co.zm",
                    "Lusaka, Zambia",
                    1125000.0,
                    "40% upfront, 40% at milestone, 20% on completion",
                    "ongoing",
                    12,
                    1,
                    37500.0,
                    "2026-01-15",
                    "2026-04-10",
                    "Full e-commerce redesign with payment integration and marketing automation.",
                ),
            )
            project_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

            conn.executemany(
                "INSERT INTO expenses (project_id, amount, description, category, expense_date) VALUES (?, ?, ?, ?, ?)",
                [
                    (project_id, 87500.0, "UI/UX design tools & assets", "Software", "2026-01-20"),
                    (project_id, 30000.0, "Hosting setup - first quarter", "Infrastructure", "2026-01-25"),
                    (project_id, 20000.0, "Stock photography license", "Marketing", "2026-02-01"),
                ],
            )
            conn.executemany(
                "INSERT INTO payments_received (project_id, amount, description, payment_date) VALUES (?, ?, ?, ?)",
                [
                    (project_id, 450000.0, "Upfront payment (40%)", "2026-01-18"),
                    (project_id, 450000.0, "Milestone payment (40%)", "2026-02-28"),
                ],
            )
            conn.executemany(
                """
                INSERT INTO subcontractors
                (project_id, name, company, contact_email, contract_amount, amount_paid, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (project_id, "James Banda", "DevCraft Solutions", "james@devcraft.co", 200000.0, 100000.0, "Backend API development"),
                ],
            )

            conn.execute(
                """
                INSERT INTO projects (
                    name, client_company, client_contact_name, client_email, client_phone,
                    client_website, client_location, contract_amount, payment_terms,
                    status, duration_weeks, has_monthly_maintenance, start_date, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Social Media Marketing Campaign",
                    "FreshFarm Organics",
                    "Peter Chanda",
                    "peter@freshfarm.co",
                    "+260 966 112 233",
                    "https://freshfarmorganics.co.zm",
                    "Ndola, Zambia",
                    300000.0,
                    "50% upfront, 50% on completion",
                    "pending",
                    8,
                    0,
                    "2026-03-01",
                    "3-month social media strategy, content creation, and paid ads management.",
                ),
            )

            conn.execute(
                """
                INSERT INTO projects (
                    name, client_company, client_contact_name, client_email, client_phone,
                    client_website, client_location, contract_amount, payment_terms,
                    status, duration_weeks, has_monthly_maintenance, maintenance_amount,
                    start_date, end_date, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Corporate Website & SEO",
                    "LegalEase Partners",
                    "Grace Tembo",
                    "grace@legalease.co",
                    "+260 977 445 566",
                    "https://legalease.co.zm",
                    "Lusaka, Zambia",
                    700000.0,
                    "30% upfront, 70% on completion",
                    "completed",
                    10,
                    1,
                    20000.0,
                    "2025-10-01",
                    "2025-12-15",
                    "Corporate website build with SEO optimization and monthly maintenance.",
                ),
            )

            conn.executemany(
                "INSERT INTO expenses (project_id, amount, description, category, expense_date) VALUES (?, ?, ?, ?, ?)",
                [(None, 15000.0, "Office internet - March", "Utilities", "2026-03-01"),
                 (None, 28000.0, "Staff training workshop", "HR", "2026-02-15")],
            )

        else:
            ensure_demo_users(conn)

        seed_financials(conn)


if __name__ == "__main__":
    seed()
    print("Database seeded successfully.")

from __future__ import annotations

from datetime import date, datetime


def kwacha(value: float | None) -> str:
    return f"K {value or 0:,.2f}"


def days_remaining(end_date: str | None) -> int | None:
    if not end_date:
        return None
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    delta = (end - date.today()).days
    return max(delta, 0) if delta >= 0 else delta


def log_audit(conn, user, action: str, entity_type: str = "", entity_id: int | None = None, details: str = ""):
    conn.execute(
        """
        INSERT INTO audit_log (user_id, user_name, action, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user["id"] if user else None, user["name"] if user else "System", action, entity_type, entity_id, details),
    )


def total_bank_balance(conn) -> float:
    row = conn.execute("SELECT COALESCE(SUM(balance), 0) AS t FROM bank_accounts WHERE is_active = 1").fetchone()
    return row["t"]


def total_reserves(conn) -> float:
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM company_reserves").fetchone()
    return row["t"]


def total_investment_profits(conn) -> float:
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM investment_profits").fetchone()
    return row["t"]


def sync_investment_return(conn, investment_id: int):
    total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM investment_profits WHERE investment_id = ?",
        (investment_id,),
    ).fetchone()["t"]
    conn.execute(
        "UPDATE company_investments SET actual_return = ? WHERE id = ?",
        (total, investment_id),
    )


def fetch_investments(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM company_investments ORDER BY investment_date DESC"
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["profit_entries"] = conn.execute(
            "SELECT * FROM investment_profits WHERE investment_id = ? ORDER BY profit_date DESC",
            (item["id"],),
        ).fetchall()
        item["total_profit"] = sum(p["amount"] for p in item["profit_entries"])
        result.append(item)
    return result


def company_total_profit(conn, projects: list[dict]) -> dict:
    project_revenue = sum(p["total_received"] for p in projects)
    project_expenses = sum(p["total_expenses"] for p in projects)
    investment_profit = total_investment_profits(conn)
    general_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE project_id IS NULL"
    ).fetchone()["t"]
    total_revenue = project_revenue + investment_profit
    total_expenses = project_expenses + general_expenses
    return {
        "project_revenue": project_revenue,
        "investment_profit": investment_profit,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_profit": total_revenue - total_expenses,
    }


def total_investments(conn) -> float:
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM company_investments").fetchone()
    return row["t"]


def get_main_bank(conn):
    row = conn.execute(
        "SELECT * FROM bank_accounts WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def company_financial_position(conn) -> dict:
    bank = get_main_bank(conn)
    if bank:
        bank_balance = bank["balance"]
    else:
        row = conn.execute("SELECT bank_balance FROM company_settings WHERE id = 1").fetchone()
        bank_balance = row["bank_balance"] if row else 0
    reserves = total_reserves(conn)
    return {
        "bank": bank,
        "bank_balance": bank_balance,
        "reserves": reserves,
        "total_available": bank_balance + reserves,
    }


def company_liquidity(conn) -> dict:
    """Legacy alias — use company_financial_position instead."""
    pos = company_financial_position(conn)
    return {
        "banks": [pos["bank"]] if pos["bank"] else [],
        "bank_total": pos["bank_balance"],
        "reserves": pos["reserves"],
        "total_liquidity": pos["total_available"],
        "economic_strength": pos["total_available"],
    }


def client_slug(company: str) -> str:
    return company.strip().lower().replace(" ", "-").replace("/", "-")


def fetch_clients(projects: list[dict]) -> list[dict]:
    clients_map: dict[str, dict] = {}
    for p in projects:
        company = (p.get("client_company") or "Unknown").strip()
        key = client_slug(company)
        if key not in clients_map:
            clients_map[key] = {
                "slug": key,
                "company": company,
                "contact_name": p.get("client_contact_name"),
                "email": p.get("client_email"),
                "phone": p.get("client_phone"),
                "website": p.get("client_website"),
                "location": p.get("client_location") or p.get("client_address"),
                "address": p.get("client_address"),
                "projects": [],
                "total_contracts": 0.0,
                "total_received": 0.0,
                "total_expenses": 0.0,
                "completed_count": 0,
                "active_count": 0,
            }
        c = clients_map[key]
        c["projects"].append(p)
        c["total_contracts"] += p["contract_amount"]
        c["total_received"] += p["total_received"]
        c["total_expenses"] += p["total_expenses"]
        if p["status"] == "completed":
            c["completed_count"] += 1
        elif p["status"] in ("ongoing", "pending"):
            c["active_count"] += 1
        for src, dst in [
            ("client_contact_name", "contact_name"),
            ("client_email", "email"),
            ("client_phone", "phone"),
            ("client_website", "website"),
        ]:
            if p.get(src) and not c.get(dst):
                c[dst] = p[src]
        loc = p.get("client_location") or p.get("client_address")
        if loc and not c.get("location"):
            c["location"] = loc

    result = list(clients_map.values())
    for c in result:
        c["project_count"] = len(c["projects"])
    result.sort(key=lambda x: x["company"].lower())
    return result


def monthly_financials(conn, year: int) -> list[dict]:
    months = []
    for month in range(1, 13):
        revenue = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS t FROM payments_received
            WHERE strftime('%Y', payment_date) = ? AND strftime('%m', payment_date) = ?
            """,
            (str(year), f"{month:02d}"),
        ).fetchone()["t"]
        investment_profit = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS t FROM investment_profits
            WHERE strftime('%Y', profit_date) = ? AND strftime('%m', profit_date) = ?
            """,
            (str(year), f"{month:02d}"),
        ).fetchone()["t"]
        total_revenue = revenue + investment_profit
        project_expenses = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS t FROM expenses
            WHERE project_id IS NOT NULL
            AND strftime('%Y', expense_date) = ? AND strftime('%m', expense_date) = ?
            """,
            (str(year), f"{month:02d}"),
        ).fetchone()["t"]
        company_expenses = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS t FROM expenses
            WHERE project_id IS NULL
            AND strftime('%Y', expense_date) = ? AND strftime('%m', expense_date) = ?
            """,
            (str(year), f"{month:02d}"),
        ).fetchone()["t"]
        total_expenses = project_expenses + company_expenses
        profit = total_revenue - total_expenses
        target_row = conn.execute(
            "SELECT * FROM monthly_targets WHERE year = ? AND month = ?", (year, month)
        ).fetchone()
        months.append(
            {
                "month": month,
                "project_revenue": revenue,
                "investment_profit": investment_profit,
                "revenue": total_revenue,
                "expenses": total_expenses,
                "profit": profit,
                "revenue_target": target_row["revenue_target"] if target_row else 0,
                "profit_target": target_row["profit_target"] if target_row else 0,
                "investment_target": target_row["investment_target"] if target_row else 0,
            }
        )
    return months


def month_report_detail(conn, year: int, month: int) -> dict:
    """Line-item detail for a single month's financial PDF report."""
    mm = f"{month:02d}"
    yy = str(year)

    payments = conn.execute(
        """
        SELECT pr.*, p.name AS project_name, p.client_company
        FROM payments_received pr
        LEFT JOIN projects p ON p.id = pr.project_id
        WHERE strftime('%Y', pr.payment_date) = ? AND strftime('%m', pr.payment_date) = ?
        ORDER BY pr.payment_date
        """,
        (yy, mm),
    ).fetchall()

    expenses = conn.execute(
        """
        SELECT e.*, p.name AS project_name
        FROM expenses e
        LEFT JOIN projects p ON p.id = e.project_id
        WHERE strftime('%Y', e.expense_date) = ? AND strftime('%m', e.expense_date) = ?
        ORDER BY e.expense_date
        """,
        (yy, mm),
    ).fetchall()

    projects = conn.execute(
        """
        SELECT p.id, p.name, p.client_company, p.status,
            COALESCE((
                SELECT SUM(amount) FROM payments_received pr
                WHERE pr.project_id = p.id
                AND strftime('%Y', pr.payment_date) = ? AND strftime('%m', pr.payment_date) = ?
            ), 0) AS month_received,
            COALESCE((
                SELECT SUM(amount) FROM expenses ex
                WHERE ex.project_id = p.id
                AND strftime('%Y', ex.expense_date) = ? AND strftime('%m', ex.expense_date) = ?
            ), 0) AS month_expenses
        FROM projects p
        WHERE p.id IN (
            SELECT project_id FROM payments_received
            WHERE strftime('%Y', payment_date) = ? AND strftime('%m', payment_date) = ?
            UNION
            SELECT project_id FROM expenses
            WHERE project_id IS NOT NULL
            AND strftime('%Y', expense_date) = ? AND strftime('%m', expense_date) = ?
        )
        ORDER BY p.client_company
        """,
        (yy, mm, yy, mm, yy, mm, yy, mm),
    ).fetchall()

    month_data = next((m for m in monthly_financials(conn, year) if m["month"] == month), None)

    return {
        "payments": [dict(r) for r in payments],
        "expenses": [dict(r) for r in expenses],
        "projects": [dict(r) for r in projects],
        "month_data": month_data,
    }

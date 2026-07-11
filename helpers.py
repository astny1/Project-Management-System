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


def collection_status(contract: float, received: float) -> str:
    """pending | partial | collected"""
    if contract <= 0:
        return "none"
    if received >= contract:
        return "collected"
    if received > 0:
        return "partial"
    return "pending"


def project_profit_amount(received: float, expenses: float, sub_paid: float = 0) -> float:
    return received - expenses - sub_paid


def fetch_projects(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.*,
            COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.project_id = p.id), 0) AS total_expenses,
            COALESCE((SELECT SUM(amount) FROM payments_received pr WHERE pr.project_id = p.id), 0) AS total_received,
            COALESCE((SELECT SUM(amount_paid) FROM subcontractors s WHERE s.project_id = p.id), 0) AS total_sub_paid,
            (SELECT COUNT(*) FROM subcontractors s WHERE s.project_id = p.id) AS subcontractor_count
        FROM projects p
        ORDER BY CASE p.status WHEN 'ongoing' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, p.updated_at DESC
        """
    ).fetchall()
    projects = []
    for row in rows:
        item = dict(row)
        item["remaining_balance"] = max(item["contract_amount"] - item["total_received"], 0)
        item["collection_status"] = collection_status(item["contract_amount"], item["total_received"])
        item["project_profit"] = project_profit_amount(
            item["total_received"], item["total_expenses"], item["total_sub_paid"]
        )
        item["days_left"] = days_remaining(item.get("end_date"))
        projects.append(item)
    return projects


def company_total_profit(conn, projects: list[dict]) -> dict:
    """Company-wide financial summary (ZMW)."""
    total_contract_value = sum(p["contract_amount"] for p in projects)
    cash_from_projects = sum(p["total_received"] for p in projects)
    project_expenses = sum(p["total_expenses"] for p in projects)
    subcontractor_paid = sum(p.get("total_sub_paid", 0) for p in projects)
    project_profit = sum(
        project_profit_amount(p["total_received"], p["total_expenses"], p.get("total_sub_paid", 0))
        for p in projects
    )
    investment_profit = total_investment_profits(conn)
    general_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE project_id IS NULL"
    ).fetchone()["t"]

    total_expenses = project_expenses + general_expenses + subcontractor_paid
    remaining_to_collect = sum(max(p["contract_amount"] - p["total_received"], 0) for p in projects)
    total_revenue = project_profit + investment_profit
    net_profit = total_revenue - general_expenses

    return {
        "total_contract_value": total_contract_value,
        "cash_from_projects": cash_from_projects,
        "income_received": cash_from_projects,
        "project_profit": project_profit,
        "investment_profit": investment_profit,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "project_expenses": project_expenses,
        "company_expenses": general_expenses,
        "subcontractor_paid": subcontractor_paid,
        "remaining_to_collect": remaining_to_collect,
        "net_profit": net_profit,
        # Legacy keys
        "total_income": cash_from_projects,
        "project_revenue": project_profit,
        "total_profit": net_profit,
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
        project_income = conn.execute(
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
        project_profit = project_income - project_expenses
        total_revenue = project_profit + investment_profit
        total_expenses = project_expenses + company_expenses
        profit = total_revenue - company_expenses
        target_row = conn.execute(
            "SELECT * FROM monthly_targets WHERE year = ? AND month = ?", (year, month)
        ).fetchone()
        months.append(
            {
                "month": month,
                "project_income": project_income,
                "project_expenses": project_expenses,
                "project_profit": project_profit,
                "project_revenue": project_profit,
                "investment_profit": investment_profit,
                "revenue": total_revenue,
                "company_expenses": company_expenses,
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


def next_document_number(conn, table: str, column: str, prefix: str, year: int | None = None) -> str:
    year = year or date.today().year
    pattern = f"{prefix}-{year}-%"
    row = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE ? ORDER BY {column} DESC LIMIT 1",
        (pattern + "%",),
    ).fetchone()
    seq = 1
    if row and row[column]:
        try:
            seq = int(str(row[column]).split("-")[-1]) + 1
        except ValueError:
            seq = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {column} LIKE ?", (pattern + "%",)).fetchone()["c"] + 1
    return f"{prefix}-{year}-{seq:03d}"


def parse_line_items(form) -> list[dict]:
    descriptions = form.getlist("item_description")
    quantities = form.getlist("item_quantity")
    prices = form.getlist("item_unit_price")
    items = []
    for i, desc in enumerate(descriptions):
        desc = (desc or "").strip()
        if not desc:
            continue
        qty = float(quantities[i] if i < len(quantities) and quantities[i] else 1)
        price = float(prices[i] if i < len(prices) and prices[i] else 0)
        items.append({"description": desc, "quantity": qty, "unit_price": price, "line_total": qty * price})
    return items


def document_totals(items: list[dict], tax_rate: float = 0) -> dict:
    subtotal = sum(i["line_total"] for i in items)
    tax_amount = subtotal * (tax_rate / 100)
    return {"subtotal": subtotal, "tax_rate": tax_rate, "tax_amount": tax_amount, "total": subtotal + tax_amount}


def dashboard_alerts(conn, projects: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    today = date.today().isoformat()

    for p in projects:
        if p["status"] == "ongoing" and p.get("remaining_balance", 0) > 0:
            alerts.append({
                "type": "collection",
                "severity": "warning",
                "message": f"{p['client_company']}: {kwacha(p['remaining_balance'])} still to collect on {p['name']}",
                "url": f"/projects/{p['id']}",
            })
        days = p.get("days_left")
        if p["status"] == "ongoing" and days is not None and days <= 7:
            alerts.append({
                "type": "deadline",
                "severity": "urgent" if days <= 3 else "warning",
                "message": f"{p['name']} due in {days} day(s)" if days > 0 else f"{p['name']} is overdue",
                "url": f"/projects/{p['id']}",
            })
        if p.get("has_monthly_maintenance") and p["status"] == "ongoing":
            pass  # summarized below

    retainer_count = sum(1 for p in projects if p.get("has_monthly_maintenance") and p["status"] == "ongoing")
    if retainer_count:
        mrr = sum(p.get("maintenance_amount", 0) for p in projects if p.get("has_monthly_maintenance") and p["status"] == "ongoing")
        alerts.append({
            "type": "maintenance",
            "severity": "info",
            "message": f"{retainer_count} retainer client(s) — MRR {kwacha(mrr)}",
            "url": "/maintenance",
        })

    overdue = conn.execute(
        """
        SELECT id, invoice_number, client_company, total, amount_paid, due_date
        FROM invoices
        WHERE status IN ('unpaid', 'partial', 'overdue')
        AND due_date IS NOT NULL AND due_date < ?
        ORDER BY due_date
        LIMIT 10
        """,
        (today,),
    ).fetchall()
    for inv in overdue:
        due = inv["total"] - inv["amount_paid"]
        alerts.append({
            "type": "invoice",
            "severity": "urgent",
            "message": f"Overdue invoice {inv['invoice_number']} — {inv['client_company']} ({kwacha(due)} due)",
            "url": f"/invoices/{inv['id']}/pdf",
        })

    pending_leads = conn.execute(
        "SELECT COUNT(*) AS c FROM leads WHERE status IN ('new', 'contacted', 'proposal')"
    ).fetchone()["c"]
    if pending_leads:
        alerts.append({
            "type": "leads",
            "severity": "info",
            "message": f"{pending_leads} active lead(s) in pipeline",
            "url": "/leads",
        })

    try:
        tax_rows = conn.execute(
            """
            SELECT title, amount, due_date FROM tax_obligations
            WHERE status = 'pending' AND due_date <= date('now', '+14 days')
            ORDER BY due_date LIMIT 5
            """
        ).fetchall()
        for t in tax_rows:
            alerts.append({
                "type": "tax",
                "severity": "urgent" if t["due_date"] and t["due_date"] <= today else "warning",
                "message": f"ZRA/Tax due: {t['title']} — {kwacha(t['amount'])} by {t['due_date'] or '—'}",
                "url": "/tax",
            })
    except Exception:
        pass

    return alerts[:15]


def cash_flow_forecast(conn, projects: list[dict]) -> dict:
    """Simple 3-month cash flow projection (ZMW)."""
    position = company_financial_position(conn)
    balance = position["bank_balance"]
    still_collect = sum(max(p.get("remaining_balance", 0), 0) for p in projects)
    mrr = sum(
        p.get("maintenance_amount", 0)
        for p in projects
        if p.get("has_monthly_maintenance") and p["status"] == "ongoing"
    )

    avg_expense = conn.execute(
        """
        SELECT COALESCE(AVG(m), 0) AS avg FROM (
            SELECT SUM(amount) AS m FROM expenses
            WHERE expense_date >= date('now', '-90 days')
            GROUP BY strftime('%Y-%m', expense_date)
        )
        """
    ).fetchone()["avg"]

    tax_next = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS t FROM tax_obligations
        WHERE status = 'pending' AND due_date <= date('now', '+90 days')
        """
    ).fetchone()["t"]

    collect_per_month = still_collect / 3 if still_collect else 0
    points = []
    running = balance
    labels = ["Month 1", "Month 2", "Month 3"]
    for i, label in enumerate(labels):
        inflows = mrr + collect_per_month
        outflows = avg_expense + (tax_next if i == 0 else 0)
        running = running + inflows - outflows
        points.append({
            "label": label,
            "inflows": inflows,
            "outflows": outflows,
            "balance": running,
        })

    return {
        "starting_balance": balance,
        "still_to_collect": still_collect,
        "mrr": mrr,
        "avg_monthly_expense": avg_expense,
        "tax_due_90d": tax_next,
        "points": points,
        "labels": [p["label"] for p in points],
        "balances": [p["balance"] for p in points],
        "inflows": [p["inflows"] for p in points],
        "outflows": [p["outflows"] for p in points],
    }

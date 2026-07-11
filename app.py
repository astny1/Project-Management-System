from __future__ import annotations

import json
import os
from calendar import month_name
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db, migrate_db
from approvals import create_approval, review_approval
from helpers import (
    collection_status,
    company_financial_position,
    company_total_profit,
    dashboard_alerts,
    days_remaining,
    document_totals,
    fetch_clients,
    fetch_investments,
    kwacha,
    log_audit,
    month_report_detail,
    monthly_financials,
    next_document_number,
    parse_line_items,
    project_profit_amount,
    sync_investment_return,
    total_investment_profits,
    total_reserves,
)
from pdf_reports import build_financial_report_pdf, build_invoice_pdf, build_project_report_pdf, build_quotation_pdf
from permissions import can, nav_groups, nav_items, requires_approval, role_label

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "growthhive-dev-secret-change-in-production")
app.jinja_env.filters["money"] = kwacha


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not can(g.user["role"], permission):
                flash("You do not have access to this section.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_permissions():
    pending = 0
    if g.user and g.user["role"] == "admin":
        try:
            with get_db() as conn:
                pending = conn.execute(
                    "SELECT COUNT(*) AS c FROM pending_approvals WHERE status='pending'"
                ).fetchone()["c"]
        except Exception:
            pending = 0
    role = g.user["role"] if g.user else None
    return {
        "can_access": lambda p: can(role, p),
        "user_nav": nav_items(role),
        "nav_groups": nav_groups(role),
        "role_label": role_label,
        "pending_approvals": pending,
        "needs_approval": requires_approval(role),
    }


@app.before_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        with get_db() as conn:
            g.user = conn.execute(
                "SELECT id, email, name, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()


def project_totals(conn, project_id: int) -> dict:
    expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE project_id = ?", (project_id,)
    ).fetchone()["total"]
    received = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments_received WHERE project_id = ?", (project_id,)
    ).fetchone()["total"]
    sub_paid = conn.execute(
        "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM subcontractors WHERE project_id = ?", (project_id,)
    ).fetchone()["total"]
    project = conn.execute("SELECT contract_amount FROM projects WHERE id = ?", (project_id,)).fetchone()
    contract = project["contract_amount"] if project else 0
    profit = project_profit_amount(received, expenses, sub_paid)
    return {
        "expenses": expenses,
        "received": received,
        "sub_paid": sub_paid,
        "remaining": max(contract - received, 0),
        "profit": profit,
        "total_revenue": profit,
        "profit_estimate": profit,
        "collection_status": collection_status(contract, received),
    }


def fetch_projects(conn):
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


def dashboard_stats(conn, projects):
    position = company_financial_position(conn)
    company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
    financials = company_total_profit(conn, projects)
    return {
        "ongoing": sum(1 for p in projects if p["status"] == "ongoing"),
        "pending": sum(1 for p in projects if p["status"] == "pending"),
        "completed": sum(1 for p in projects if p["status"] == "completed"),
        "position": position,
        "reserves": total_reserves(conn),
        "monthly_profit_target": company["monthly_profit_target"] if company else 0,
        # Financial summary
        "total_contracts": financials["total_contract_value"],
        "total_received": financials["cash_from_projects"],
        "income_received": financials["income_received"],
        "total_income": financials["income_received"],
        "project_profit": financials["project_profit"],
        "total_expenses": financials["total_expenses"],
        "remaining_to_collect": financials["remaining_to_collect"],
        "investment_profit": financials["investment_profit"],
        "total_revenue": financials["total_revenue"],
        "profit": financials["net_profit"],
        "net_profit": financials["net_profit"],
        "project_expenses": financials["project_expenses"],
        "company_expenses": financials["company_expenses"],
    }


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                log_audit(conn, dict(user), "Logged in", "auth", user["id"], email)
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    if g.user:
        with get_db() as conn:
            log_audit(conn, g.user, "Logged out", "auth", g.user["id"])
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as conn:
        projects = fetch_projects(conn)
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        stats = dashboard_stats(conn, projects)
        clients = fetch_clients(projects)
        recent_logs = conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        alerts = dashboard_alerts(conn, projects)
    return render_template(
        "dashboard.html",
        projects=projects,
        company=company,
        stats=stats,
        clients=clients,
        recent_logs=recent_logs,
        alerts=alerts,
    )


@app.route("/clients")
@permission_required("clients_view")
def clients():
    q = request.args.get("q", "").strip().lower()
    with get_db() as conn:
        projects = fetch_projects(conn)
        all_clients = fetch_clients(projects)
        if q:
            all_clients = [
                c for c in all_clients
                if q in c["company"].lower()
                or q in (c.get("email") or "").lower()
                or q in (c.get("location") or "").lower()
            ]
    return render_template("clients.html", clients=all_clients, search_q=q)


@app.route("/clients/<slug>")
@permission_required("clients_view")
def client_detail(slug):
    with get_db() as conn:
        projects = fetch_projects(conn)
        clients_list = fetch_clients(projects)
        client = next((c for c in clients_list if c["slug"] == slug), None)
        if not client:
            flash("Client not found.", "error")
            return redirect(url_for("clients"))
    return render_template("client_detail.html", client=client)


@app.route("/reserves")
@permission_required("reserves_view")
def reserves():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM company_reserves ORDER BY reserve_date DESC").fetchall()
        total = total_reserves(conn)
        position = company_financial_position(conn)
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
    return render_template(
        "reserves.html", reserves=items, total=total, company=company, position=position
    )


@app.route("/reserves/bank", methods=["POST"])
@admin_required
def update_main_bank():
    with get_db() as conn:
        balance = float(request.form.get("balance") or 0)
        bank = conn.execute("SELECT id FROM bank_accounts WHERE is_active = 1 LIMIT 1").fetchone()
        if bank:
            conn.execute(
                "UPDATE bank_accounts SET balance=?, updated_at=datetime('now') WHERE id=?",
                (balance, bank["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO bank_accounts (bank_name, account_label, account_number, balance, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Stanbic Bank Zambia",
                    "GrowthHive Media — Main Account",
                    request.form.get("account_number", "9130009876543").strip(),
                    balance,
                    "Primary company operating account",
                ),
            )
        conn.execute("UPDATE company_settings SET bank_balance=? WHERE id=1", (balance,))
        log_audit(conn, g.user, "Updated Stanbic bank balance", "bank", 1, kwacha(balance))
    flash("Stanbic account balance updated.", "success")
    return redirect(url_for("reserves"))


@app.route("/reserves/add", methods=["POST"])
@admin_required
def add_reserve():
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO company_reserves (name, amount, purpose, category, reserve_date, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.form.get("name", "").strip(),
                float(request.form.get("amount") or 0),
                request.form.get("purpose", "").strip(),
                request.form.get("category", "").strip(),
                request.form.get("reserve_date") or datetime.now().strftime("%Y-%m-%d"),
                request.form.get("notes", "").strip(),
            ),
        )
        log_audit(conn, g.user, "Added company reserve", "reserve", None, request.form.get("name"))
    flash("Reserve added.", "success")
    return redirect(url_for("reserves"))


@app.route("/reserves/investments", methods=["POST"])
@admin_required
def add_investment():
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO company_investments
            (name, business_type, amount, expected_return, actual_return, investment_date, status, notes)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                request.form.get("name", "").strip(),
                request.form.get("business_type", "").strip(),
                float(request.form.get("amount") or 0),
                float(request.form.get("expected_return") or 0),
                request.form.get("investment_date") or datetime.now().strftime("%Y-%m-%d"),
                request.form.get("status", "active"),
                request.form.get("notes", "").strip(),
            ),
        )
        log_audit(conn, g.user, "Added investment", "investment", None, request.form.get("name"))
    flash("Investment recorded.", "success")
    return redirect(url_for("investments"))


@app.route("/investments")
@admin_required
def investments():
    with get_db() as conn:
        items = fetch_investments(conn)
        inv_total = conn.execute("SELECT COALESCE(SUM(amount),0) AS t FROM company_investments").fetchone()["t"]
        profit_total = total_investment_profits(conn)
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        profit_log = conn.execute(
            """
            SELECT ip.*, ci.name AS business_name FROM investment_profits ip
            JOIN company_investments ci ON ci.id = ip.investment_id
            ORDER BY ip.profit_date DESC LIMIT 50
            """
        ).fetchall()
    return render_template(
        "investments.html",
        investments=items,
        inv_total=inv_total,
        profit_total=profit_total,
        company=company,
        profit_log=profit_log,
    )


@app.route("/investments/profit", methods=["POST"])
@admin_required
def add_investment_profit():
    investment_id = int(request.form.get("investment_id"))
    amount = float(request.form.get("amount") or 0)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO investment_profits (investment_id, amount, profit_date, description)
            VALUES (?, ?, ?, ?)
            """,
            (
                investment_id,
                amount,
                request.form.get("profit_date") or datetime.now().strftime("%Y-%m-%d"),
                request.form.get("description", "").strip(),
            ),
        )
        sync_investment_return(conn, investment_id)
        inv = conn.execute("SELECT name FROM company_investments WHERE id=?", (investment_id,)).fetchone()
        log_audit(conn, g.user, "Recorded investment profit", "investment", investment_id, f"{kwacha(amount)} from {inv['name']}")
    flash("Investment profit added to total revenue.", "success")
    return redirect(url_for("investments"))


@app.route("/expenses")
@permission_required("expenses_view")
def company_expenses():
    with get_db() as conn:
        project_expenses = conn.execute(
            """
            SELECT e.*, p.name AS project_name FROM expenses e
            LEFT JOIN projects p ON p.id = e.project_id
            WHERE e.project_id IS NOT NULL ORDER BY e.expense_date DESC
            """
        ).fetchall()
        general_expenses = conn.execute(
            "SELECT * FROM expenses WHERE project_id IS NULL ORDER BY expense_date DESC"
        ).fetchall()
        total_project = sum(e["amount"] for e in project_expenses)
        total_general = sum(e["amount"] for e in general_expenses)
        projects = conn.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    return render_template(
        "expenses.html",
        project_expenses=project_expenses,
        general_expenses=general_expenses,
        total_project=total_project,
        total_general=total_general,
        projects=projects,
    )


@app.route("/expenses/add", methods=["POST"])
@login_required
def add_company_expense():
    if g.user["role"] not in ("admin", "sales_manager"):
        flash("You cannot add company expenses.", "error")
        return redirect(url_for("company_expenses"))
    project_id = request.form.get("project_id")
    payload = {
        "project_id": int(project_id) if project_id else None,
        "amount": float(request.form.get("amount") or 0),
        "description": request.form.get("description", "").strip(),
        "category": request.form.get("category", "").strip(),
        "expense_date": request.form.get("expense_date") or datetime.now().strftime("%Y-%m-%d"),
    }
    with get_db() as conn:
        if requires_approval(g.user["role"]):
            create_approval(conn, g.user, "add_expense", payload, "expense", payload.get("project_id"))
            flash("Expense submitted for admin approval.", "warning")
        else:
            conn.execute(
                "INSERT INTO expenses (project_id, amount, description, category, expense_date) VALUES (?, ?, ?, ?, ?)",
                (payload["project_id"], payload["amount"], payload["description"], payload["category"], payload["expense_date"]),
            )
            log_audit(conn, g.user, "Added expense", "expense", payload.get("project_id"))
            flash("Expense recorded.", "success")
    return redirect(url_for("company_expenses"))


@app.route("/accounting")
@permission_required("accounting_view")
def accounting():
    year = int(request.args.get("year", datetime.now().year))
    with get_db() as conn:
        months = monthly_financials(conn, year)
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        ytd_revenue = sum(m["revenue"] for m in months)
        ytd_profit = sum(m["profit"] for m in months)
        ytd_target = sum(m["profit_target"] for m in months)
        ytd_investment = sum(m["investment_profit"] for m in months)
        ytd_project_profit = sum(m["project_profit"] for m in months)
        ytd_project_income = sum(m["project_income"] for m in months)
    chart_labels = [month_name[m["month"]][:3] for m in months]
    return render_template(
        "accounting.html",
        months=months,
        company=company,
        year=year,
        current_month=datetime.now().month,
        ytd_revenue=ytd_revenue,
        ytd_profit=ytd_profit,
        ytd_target=ytd_target,
        ytd_investment=ytd_investment,
        ytd_project_profit=ytd_project_profit,
        ytd_project_income=ytd_project_income,
        chart_labels=json.dumps(chart_labels),
        chart_profit=json.dumps([m["profit"] for m in months]),
        chart_target=json.dumps([m["profit_target"] for m in months]),
        chart_revenue=json.dumps([m["revenue"] for m in months]),
        chart_expenses=json.dumps([m["expenses"] for m in months]),
        chart_investment=json.dumps([m["investment_profit"] for m in months]),
    )


@app.route("/accounting/targets", methods=["POST"])
@admin_required
def update_targets():
    year = int(request.form.get("year", datetime.now().year))
    month = int(request.form.get("month"))
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO monthly_targets (year, month, revenue_target, profit_target, investment_target)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(year, month) DO UPDATE SET
                revenue_target=excluded.revenue_target,
                profit_target=excluded.profit_target,
                investment_target=excluded.investment_target
            """,
            (
                year, month,
                float(request.form.get("revenue_target") or 0),
                float(request.form.get("profit_target") or 0),
                float(request.form.get("investment_target") or 0),
            ),
        )
        log_audit(conn, g.user, "Updated monthly targets", "target", month, f"Year {year}")
    flash("Monthly targets updated.", "success")
    return redirect(url_for("accounting", year=year))


@app.route("/accounting/report/pdf")
@permission_required("reports")
def accounting_report_pdf():
    year = int(request.args.get("year", datetime.now().year))
    scope = request.args.get("scope", "month")
    month = int(request.args.get("month", datetime.now().month))

    with get_db() as conn:
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        position = company_financial_position(conn)
        months = monthly_financials(conn, year)
        detail = month_report_detail(conn, year, month) if scope == "month" else None

    buffer = build_financial_report_pdf(
        dict(company),
        scope=scope,
        year=year,
        month=month if scope == "month" else None,
        month_data=detail["month_data"] if detail else None,
        months=months,
        payments=detail["payments"] if detail else [],
        expenses=detail["expenses"] if detail else [],
        projects=detail["projects"] if detail else [],
        position=position,
        generated_by=g.user["name"],
    )
    if scope == "month":
        filename = f"GrowthHive_Financial_{month_name[month]}_{year}.pdf"
    else:
        filename = f"GrowthHive_Financial_Year_{year}.pdf"
    with get_db() as conn:
        log_audit(conn, g.user, f"Generated financial report ({scope})", "report", None, filename)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/auditing")
@admin_required
def auditing():
    with get_db() as conn:
        logs = conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return render_template("auditing.html", logs=logs)


@app.route("/maintenance")
@permission_required("maintenance_view")
def maintenance():
    with get_db() as conn:
        projects = conn.execute(
            """
            SELECT p.*,
                COALESCE((SELECT SUM(amount) FROM payments_received pr WHERE pr.project_id = p.id), 0) AS total_received
            FROM projects p WHERE p.has_monthly_maintenance = 1
            ORDER BY CASE p.status WHEN 'ongoing' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, p.client_company
            """
        ).fetchall()
    return render_template("maintenance.html", projects=projects)


@app.route("/approvals")
@admin_required
def approvals():
    with get_db() as conn:
        pending = conn.execute(
            "SELECT * FROM pending_approvals WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()
        history = conn.execute(
            "SELECT * FROM pending_approvals WHERE status!='pending' ORDER BY reviewed_at DESC LIMIT 30"
        ).fetchall()
    return render_template("approvals.html", pending=pending, history=history)


@app.route("/approvals/<int:approval_id>/review", methods=["POST"])
@admin_required
def approvals_review(approval_id):
    approve = request.form.get("action") == "approve"
    note = request.form.get("note", "").strip()
    with get_db() as conn:
        ok = review_approval(conn, approval_id, g.user, approve, note)
    if ok:
        flash("Approved and applied." if approve else "Request rejected.", "success")
    else:
        flash("Approval not found or already processed.", "error")
    return redirect(url_for("approvals"))


@app.route("/team")
@admin_required
def team():
    with get_db() as conn:
        users = conn.execute("SELECT id, email, name, role FROM users ORDER BY role, name").fetchall()
    return render_template("team.html", users=users)


@app.route("/team/add", methods=["POST"])
@admin_required
def team_add():
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "project_manager")
    password = request.form.get("password", "").strip()
    if role not in ("admin", "sales_manager", "project_manager"):
        flash("Invalid role.", "error")
        return redirect(url_for("team"))
    if not email or not name or not password:
        flash("All fields are required.", "error")
        return redirect(url_for("team"))
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)",
                (email, generate_password_hash(password), name, role),
            )
            log_audit(conn, g.user, f"Added team member {name}", "user", None, f"{role_label(role)} — {email}")
            flash(f"User {name} added as {role_label(role)}.", "success")
        except Exception:
            flash("Email already exists.", "error")
    return redirect(url_for("team"))


@app.route("/team/<int:user_id>/role", methods=["POST"])
@admin_required
def team_update_role(user_id):
    role = request.form.get("role")
    if role not in ("admin", "sales_manager", "project_manager"):
        flash("Invalid role.", "error")
        return redirect(url_for("team"))
    with get_db() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        log_audit(conn, g.user, f"Updated user role to {role_label(role)}", "user", user_id)
    flash("Role updated.", "success")
    return redirect(url_for("team"))


def _initial_collection_amount(form, contract_amount: float) -> float:
    status = form.get("collection_status", "pending")
    if status == "full":
        return contract_amount
    if status == "partial":
        return min(float(form.get("collected_amount") or 0), contract_amount)
    return 0.0


def _record_project_payment(conn, project_id: int, amount: float, description: str):
    if amount <= 0:
        return
    payload = {
        "project_id": project_id,
        "amount": amount,
        "description": description,
        "payment_date": datetime.now().strftime("%Y-%m-%d"),
    }
    if requires_approval(g.user["role"]):
        create_approval(conn, g.user, "add_payment", payload, "project", project_id)
        flash("Initial payment submitted for admin approval.", "warning")
    else:
        conn.execute(
            "INSERT INTO payments_received (project_id, amount, description, payment_date) VALUES (?, ?, ?, ?)",
            (project_id, amount, description, payload["payment_date"]),
        )
        log_audit(conn, g.user, "Recorded initial payment", "project", project_id, kwacha(amount))


@app.route("/projects/new", methods=["GET", "POST"])
@permission_required("projects_create")
def project_new():
    if request.method == "POST":
        data = _project_form_data()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    name, client_company, client_contact_name, client_email, client_phone,
                    client_address, client_website, client_location, contract_amount, payment_terms,
                    status, duration_weeks, has_monthly_maintenance, maintenance_amount,
                    start_date, end_date, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(data.values()),
            )
            pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            log_audit(conn, g.user, "Created project", "project", pid, data["name"])
            collected = _initial_collection_amount(request.form, data["contract_amount"])
            _record_project_payment(conn, pid, collected, "Initial collection on project setup")
        flash("Project created successfully.", "success")
        return redirect(url_for("project_detail", project_id=pid))
    return render_template("project_form.html", project=None, title="New Project")


@app.route("/projects/<int:project_id>")
@permission_required("projects_view")
def project_detail(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        project = dict(project)
        project["days_left"] = days_remaining(project.get("end_date"))
        expenses = conn.execute(
            "SELECT * FROM expenses WHERE project_id = ? ORDER BY expense_date DESC", (project_id,)
        ).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments_received WHERE project_id = ? ORDER BY payment_date DESC", (project_id,)
        ).fetchall()
        subcontractors = conn.execute(
            "SELECT * FROM subcontractors WHERE project_id = ? ORDER BY name", (project_id,)
        ).fetchall()
        audits = conn.execute(
            "SELECT * FROM audit_log WHERE entity_type='project' AND entity_id=? ORDER BY created_at DESC LIMIT 20",
            (project_id,),
        ).fetchall()
        totals = project_totals(conn, project_id)
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        position = company_financial_position(conn)
        milestones = conn.execute(
            "SELECT * FROM project_milestones WHERE project_id=? ORDER BY sort_order, due_date",
            (project_id,),
        ).fetchall()
        quotations = conn.execute(
            "SELECT * FROM quotations WHERE project_id=? ORDER BY created_at DESC", (project_id,)
        ).fetchall()
        invoices = conn.execute(
            "SELECT * FROM invoices WHERE project_id=? ORDER BY created_at DESC", (project_id,)
        ).fetchall()
    return render_template(
        "project_detail.html",
        project=project, expenses=expenses, payments=payments,
        subcontractors=subcontractors, totals=totals, company=company,
        position=position, audits=audits, milestones=milestones,
        quotations=quotations, invoices=invoices,
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@permission_required("projects_edit")
def project_edit(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            data = _project_form_data()
            old_contract = project["contract_amount"]
            if requires_approval(g.user["role"]) and data["contract_amount"] != old_contract:
                create_approval(
                    conn, g.user, "edit_project_contract",
                    {"contract_amount": data["contract_amount"], "payment_terms": data["payment_terms"], "name": data["name"]},
                    "project", project_id,
                )
                data["contract_amount"] = old_contract
                flash("Contract amount change submitted for admin approval.", "warning")
            conn.execute(
                """
                UPDATE projects SET
                    name=?, client_company=?, client_contact_name=?, client_email=?,
                    client_phone=?, client_address=?, client_website=?, client_location=?,
                    contract_amount=?, payment_terms=?, status=?, duration_weeks=?,
                    has_monthly_maintenance=?, maintenance_amount=?, start_date=?, end_date=?,
                    description=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (*data.values(), project_id),
            )
            log_audit(conn, g.user, "Updated project", "project", project_id, data["name"])
            flash("Project updated.", "success")
            return redirect(url_for("project_detail", project_id=project_id))
    return render_template("project_form.html", project=project, title="Edit Project")


@app.route("/projects/<int:project_id>/expenses", methods=["POST"])
@login_required
def add_expense(project_id):
    if not can(g.user["role"], "project_expenses_request") and g.user["role"] != "admin":
        flash("You cannot add expenses.", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    payload = {
        "project_id": project_id,
        "amount": float(request.form.get("amount") or 0),
        "description": request.form.get("description", "").strip(),
        "category": request.form.get("category", "").strip(),
        "expense_date": request.form.get("expense_date") or datetime.now().strftime("%Y-%m-%d"),
    }
    with get_db() as conn:
        if requires_approval(g.user["role"]):
            create_approval(conn, g.user, "add_expense", payload, "project", project_id)
            flash("Expense submitted for admin approval.", "warning")
        else:
            conn.execute(
                "INSERT INTO expenses (project_id, amount, description, category, expense_date) VALUES (?, ?, ?, ?, ?)",
                (project_id, payload["amount"], payload["description"], payload["category"], payload["expense_date"]),
            )
            conn.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?", (project_id,))
            log_audit(conn, g.user, "Added project expense", "project", project_id)
            flash("Expense added.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/payments", methods=["POST"])
@login_required
def add_payment(project_id):
    if not can(g.user["role"], "project_payments_request") and g.user["role"] != "admin":
        flash("You cannot record payments.", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    payload = {
        "project_id": project_id,
        "amount": float(request.form.get("amount") or 0),
        "description": request.form.get("description", "").strip(),
        "payment_date": request.form.get("payment_date") or datetime.now().strftime("%Y-%m-%d"),
    }
    with get_db() as conn:
        if requires_approval(g.user["role"]):
            create_approval(conn, g.user, "add_payment", payload, "project", project_id)
            flash("Payment submitted for admin approval.", "warning")
        else:
            conn.execute(
                "INSERT INTO payments_received (project_id, amount, description, payment_date) VALUES (?, ?, ?, ?)",
                (project_id, payload["amount"], payload["description"], payload["payment_date"]),
            )
            conn.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?", (project_id,))
            log_audit(conn, g.user, "Recorded payment", "project", project_id)
            flash("Payment recorded.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/subcontractors", methods=["POST"])
@login_required
def add_subcontractor(project_id):
    if not can(g.user["role"], "subcontractors_request") and g.user["role"] != "admin":
        flash("You cannot add subcontractors.", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    payload = {
        "project_id": project_id,
        "name": request.form.get("name", "").strip(),
        "company": request.form.get("company", "").strip(),
        "contact_email": request.form.get("contact_email", "").strip(),
        "contact_phone": request.form.get("contact_phone", "").strip(),
        "contract_amount": float(request.form.get("contract_amount") or 0),
        "amount_paid": float(request.form.get("amount_paid") or 0),
        "notes": request.form.get("notes", "").strip(),
    }
    with get_db() as conn:
        if requires_approval(g.user["role"]):
            create_approval(conn, g.user, "add_subcontractor", payload, "project", project_id)
            flash("Subcontractor submitted for admin approval.", "warning")
        else:
            conn.execute(
                """
                INSERT INTO subcontractors
                (project_id, name, company, contact_email, contact_phone, contract_amount, amount_paid, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, payload["name"], payload["company"], payload["contact_email"],
                 payload["contact_phone"], payload["contract_amount"], payload["amount_paid"], payload["notes"]),
            )
            conn.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?", (project_id,))
            log_audit(conn, g.user, "Added subcontractor", "project", project_id)
            flash("Subcontractor added.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    with get_db() as conn:
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()

        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "profile":
                name = request.form.get("name", "").strip()
                email = request.form.get("email", "").strip().lower()
                current_pw = request.form.get("current_password", "")
                new_pw = request.form.get("new_password", "")
                confirm_pw = request.form.get("confirm_password", "")

                if not name or not email:
                    flash("Name and email are required.", "error")
                    return redirect(url_for("settings"))

                existing = conn.execute(
                    "SELECT id FROM users WHERE email = ? AND id != ?", (email, g.user["id"])
                ).fetchone()
                if existing:
                    flash("That email is already in use.", "error")
                    return redirect(url_for("settings"))

                updates = {"name": name, "email": email}
                if new_pw:
                    if not check_password_hash(user["password_hash"], current_pw):
                        flash("Current password is incorrect.", "error")
                        return redirect(url_for("settings"))
                    if len(new_pw) < 6:
                        flash("New password must be at least 6 characters.", "error")
                        return redirect(url_for("settings"))
                    if new_pw != confirm_pw:
                        flash("New passwords do not match.", "error")
                        return redirect(url_for("settings"))
                    conn.execute(
                        "UPDATE users SET name=?, email=?, password_hash=? WHERE id=?",
                        (name, email, generate_password_hash(new_pw), g.user["id"]),
                    )
                    log_audit(conn, g.user, "Updated profile and password", "user", g.user["id"])
                    flash("Profile and password updated.", "success")
                else:
                    conn.execute(
                        "UPDATE users SET name=?, email=? WHERE id=?",
                        (name, email, g.user["id"]),
                    )
                    log_audit(conn, g.user, "Updated profile", "user", g.user["id"])
                    flash("Profile updated.", "success")
                return redirect(url_for("settings"))

            if action == "company" and g.user["role"] == "admin":
                conn.execute(
                    """
                    UPDATE company_settings SET
                        company_name=?, tagline=?, email=?, phone=?, address=?, bank_balance=?,
                        monthly_profit_target=?, yearly_investment_goal=?
                    WHERE id=1
                    """,
                    (
                        request.form.get("company_name", "").strip(),
                        request.form.get("tagline", "").strip(),
                        request.form.get("email", "").strip(),
                        request.form.get("phone", "").strip(),
                        request.form.get("address", "").strip(),
                        float(request.form.get("bank_balance") or 0),
                        float(request.form.get("monthly_profit_target") or 0),
                        float(request.form.get("yearly_investment_goal") or 0),
                    ),
                )
                log_audit(conn, g.user, "Updated company settings", "settings", 1)
                flash("Company settings updated.", "success")
                return redirect(url_for("settings"))

            flash("Invalid settings action.", "error")
            return redirect(url_for("settings"))

    return render_template("settings.html", company=company, user=user)


@app.route("/projects/<int:project_id>/report")
@permission_required("reports")
def monthly_report(project_id):
    month = int(request.args.get("month", datetime.now().month))
    year = int(request.args.get("year", datetime.now().year))
    month_label = f"{month_name[month]} {year}"
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        expenses = conn.execute(
            "SELECT * FROM expenses WHERE project_id=? AND strftime('%m',expense_date)=? AND strftime('%Y',expense_date)=? ORDER BY expense_date",
            (project_id, f"{month:02d}", str(year)),
        ).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments_received WHERE project_id=? AND strftime('%m',payment_date)=? AND strftime('%Y',payment_date)=? ORDER BY payment_date",
            (project_id, f"{month:02d}", str(year)),
        ).fetchall()
        subcontractors = conn.execute("SELECT * FROM subcontractors WHERE project_id=? ORDER BY name", (project_id,)).fetchall()
        totals = project_totals(conn, project_id)
        position = company_financial_position(conn)
    return render_template(
        "monthly_report.html", project=project, company=company, expenses=expenses,
        payments=payments, subcontractors=subcontractors, totals=totals,
        month=month, year=year, month_label=month_label, position=position,
    )


@app.route("/projects/<int:project_id>/report/pdf")
@permission_required("reports")
def monthly_report_pdf(project_id):
    month = int(request.args.get("month", datetime.now().month))
    year = int(request.args.get("year", datetime.now().year))
    month_label = f"{month_name[month]} {year}"
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        company = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        expenses = conn.execute(
            "SELECT * FROM expenses WHERE project_id=? AND strftime('%m',expense_date)=? AND strftime('%Y',expense_date)=? ORDER BY expense_date",
            (project_id, f"{month:02d}", str(year)),
        ).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments_received WHERE project_id=? AND strftime('%m',payment_date)=? AND strftime('%Y',payment_date)=? ORDER BY payment_date",
            (project_id, f"{month:02d}", str(year)),
        ).fetchall()
        subcontractors = conn.execute("SELECT * FROM subcontractors WHERE project_id=? ORDER BY name", (project_id,)).fetchall()
        totals = project_totals(conn, project_id)
        pos = company_financial_position(conn)

    buffer = build_project_report_pdf(
        dict(company), dict(project),
        month_label=month_label,
        totals=totals,
        payments=[dict(p) for p in payments],
        expenses=[dict(e) for e in expenses],
        subcontractors=[dict(s) for s in subcontractors],
        position=pos,
        generated_by=g.user["name"],
    )
    with get_db() as conn:
        log_audit(conn, g.user, "Generated project report PDF", "project", project_id, month_label)
    filename = f"{project['name'].replace(' ', '_')}_{month_label.replace(' ', '_')}_Report.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/leads")
@permission_required("leads_view")
def leads():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC").fetchall()
    return render_template("leads.html", leads=items)


@app.route("/leads/add", methods=["POST"])
@permission_required("leads_view")
def add_lead():
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO leads (company_name, contact_name, email, phone, service_interest, estimated_value, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form.get("company_name", "").strip(),
                request.form.get("contact_name", "").strip(),
                request.form.get("email", "").strip(),
                request.form.get("phone", "").strip(),
                request.form.get("service_interest", "").strip(),
                float(request.form.get("estimated_value") or 0),
                request.form.get("status", "new"),
                request.form.get("notes", "").strip(),
            ),
        )
        log_audit(conn, g.user, "Added lead", "lead", None, request.form.get("company_name", ""))
    flash("Lead added.", "success")
    return redirect(url_for("leads"))


@app.route("/leads/<int:lead_id>/status", methods=["POST"])
@permission_required("leads_view")
def update_lead_status(lead_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE leads SET status=?, updated_at=datetime('now') WHERE id=?",
            (request.form.get("status", "new"), lead_id),
        )
    return redirect(url_for("leads"))


@app.route("/leads/<int:lead_id>/convert", methods=["POST"])
@permission_required("projects_create")
def convert_lead(lead_id):
    with get_db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            flash("Lead not found.", "error")
            return redirect(url_for("leads"))
        conn.execute(
            """
            INSERT INTO projects (
                name, client_company, client_contact_name, client_email, client_phone,
                client_address, client_website, client_location, contract_amount, payment_terms,
                status, duration_weeks, has_monthly_maintenance, maintenance_amount,
                start_date, end_date, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0, 0, NULL, NULL, ?)
            """,
            (
                f"{lead['company_name']} Project",
                lead["company_name"],
                lead["contact_name"],
                lead["email"],
                lead["phone"],
                "",
                "",
                "Kitwe, Zambia",
                lead["estimated_value"],
                "",
                lead["service_interest"] or "",
            ),
        )
        pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            "UPDATE leads SET status='won', updated_at=datetime('now') WHERE id=?",
            (lead_id,),
        )
        log_audit(conn, g.user, "Converted lead to project", "lead", lead_id, lead["company_name"])
    flash("Lead converted to project.", "success")
    return redirect(url_for("project_detail", project_id=pid))


def _client_fields_from_project(project: dict) -> dict:
    return {
        "client_company": project["client_company"],
        "client_contact": project.get("client_contact_name") or "",
        "client_email": project.get("client_email") or "",
        "client_phone": project.get("client_phone") or "",
        "client_address": project.get("client_address") or project.get("client_location") or "",
    }


@app.route("/projects/<int:project_id>/milestones", methods=["POST"])
@permission_required("projects_view")
def add_milestone(project_id):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO project_milestones (project_id, title, due_date, status, assigned_to, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                request.form.get("title", "").strip(),
                request.form.get("due_date") or None,
                request.form.get("status", "pending"),
                request.form.get("assigned_to", "").strip(),
                int(request.form.get("sort_order") or 0),
            ),
        )
        log_audit(conn, g.user, "Added milestone", "project", project_id)
    flash("Milestone added.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/quotes", methods=["GET", "POST"])
@permission_required("documents_view")
def project_quote(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        project = dict(project)
        if request.method == "POST":
            items = parse_line_items(request.form)
            if not items:
                flash("Add at least one line item.", "error")
                return redirect(url_for("project_quote", project_id=project_id))
            tax_rate = float(request.form.get("tax_rate") or 0)
            totals = document_totals(items, tax_rate)
            quote_no = next_document_number(conn, "quotations", "quote_number", "QUO")
            client = _client_fields_from_project(project)
            conn.execute(
                """
                INSERT INTO quotations (
                    quote_number, project_id, client_company, client_contact, client_email,
                    client_phone, client_address, title, subtotal, tax_rate, tax_amount, total,
                    valid_until, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_no, project_id, client["client_company"], client["client_contact"],
                    client["client_email"], client["client_phone"], client["client_address"],
                    request.form.get("title", project["name"]).strip(),
                    totals["subtotal"], totals["tax_rate"], totals["tax_amount"], totals["total"],
                    request.form.get("valid_until") or None,
                    request.form.get("status", "draft"),
                    request.form.get("notes", "").strip(),
                ),
            )
            qid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            for item in items:
                conn.execute(
                    "INSERT INTO quotation_items (quotation_id, description, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (qid, item["description"], item["quantity"], item["unit_price"]),
                )
            log_audit(conn, g.user, "Created quotation", "quotation", qid, quote_no)
            flash(f"Quotation {quote_no} created.", "success")
            return redirect(url_for("quotation_pdf", quote_id=qid))
    return render_template("document_form.html", project=project, doc_type="quotation", title="New Quotation")


@app.route("/quotes/<int:quote_id>/pdf")
@permission_required("documents_view")
def quotation_pdf(quote_id):
    with get_db() as conn:
        quote = conn.execute("SELECT * FROM quotations WHERE id=?", (quote_id,)).fetchone()
        if not quote:
            flash("Quotation not found.", "error")
            return redirect(url_for("dashboard"))
        quote = dict(quote)
        items = conn.execute(
            "SELECT * FROM quotation_items WHERE quotation_id=?", (quote_id,)
        ).fetchall()
        company = dict(conn.execute("SELECT * FROM company_settings WHERE id=1").fetchone())
    buffer = build_quotation_pdf(company, quote, [dict(i) for i in items], g.user["name"])
    return send_file(buffer, as_attachment=True, download_name=f"{quote['quote_number']}.pdf", mimetype="application/pdf")


@app.route("/projects/<int:project_id>/invoices", methods=["GET", "POST"])
@permission_required("documents_view")
def project_invoice(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            flash("Project not found.", "error")
            return redirect(url_for("dashboard"))
        project = dict(project)
        if request.method == "POST":
            items = parse_line_items(request.form)
            if not items:
                flash("Add at least one line item.", "error")
                return redirect(url_for("project_invoice", project_id=project_id))
            tax_rate = float(request.form.get("tax_rate") or 0)
            totals = document_totals(items, tax_rate)
            inv_no = next_document_number(conn, "invoices", "invoice_number", "INV")
            client = _client_fields_from_project(project)
            conn.execute(
                """
                INSERT INTO invoices (
                    invoice_number, project_id, client_company, client_contact, client_email,
                    client_phone, client_address, title, subtotal, tax_rate, tax_amount, total,
                    due_date, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inv_no, project_id, client["client_company"], client["client_contact"],
                    client["client_email"], client["client_phone"], client["client_address"],
                    request.form.get("title", project["name"]).strip(),
                    totals["subtotal"], totals["tax_rate"], totals["tax_amount"], totals["total"],
                    request.form.get("due_date") or None,
                    "unpaid",
                    request.form.get("notes", "").strip(),
                ),
            )
            iid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            for item in items:
                conn.execute(
                    "INSERT INTO invoice_items (invoice_id, description, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (iid, item["description"], item["quantity"], item["unit_price"]),
                )
            log_audit(conn, g.user, "Created invoice", "invoice", iid, inv_no)
            flash(f"Invoice {inv_no} created.", "success")
            return redirect(url_for("invoice_pdf", invoice_id=iid))
    return render_template("document_form.html", project=project, doc_type="invoice", title="New Invoice")


@app.route("/invoices/<int:invoice_id>/pdf")
@permission_required("documents_view")
def invoice_pdf(invoice_id):
    with get_db() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not invoice:
            flash("Invoice not found.", "error")
            return redirect(url_for("dashboard"))
        invoice = dict(invoice)
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)
        ).fetchall()
        company = dict(conn.execute("SELECT * FROM company_settings WHERE id=1").fetchone())
    buffer = build_invoice_pdf(company, invoice, [dict(i) for i in items], g.user["name"])
    return send_file(buffer, as_attachment=True, download_name=f"{invoice['invoice_number']}.pdf", mimetype="application/pdf")


def _project_form_data() -> dict:
    return {
        "name": request.form.get("name", "").strip(),
        "client_company": request.form.get("client_company", "").strip(),
        "client_contact_name": request.form.get("client_contact_name", "").strip(),
        "client_email": request.form.get("client_email", "").strip(),
        "client_phone": request.form.get("client_phone", "").strip(),
        "client_address": request.form.get("client_address", "").strip(),
        "client_website": request.form.get("client_website", "").strip(),
        "client_location": request.form.get("client_location", "").strip(),
        "contract_amount": float(request.form.get("contract_amount") or 0),
        "payment_terms": request.form.get("payment_terms", "").strip(),
        "status": request.form.get("status", "pending"),
        "duration_weeks": int(request.form.get("duration_weeks") or 0),
        "has_monthly_maintenance": 1 if request.form.get("has_monthly_maintenance") else 0,
        "maintenance_amount": float(request.form.get("maintenance_amount") or 0),
        "start_date": request.form.get("start_date") or None,
        "end_date": request.form.get("end_date") or None,
        "description": request.form.get("description", "").strip(),
    }


if __name__ == "__main__":
    init_db()
    migrate_db()
    from seed import seed
    seed()
    app.run(debug=True, port=5000)

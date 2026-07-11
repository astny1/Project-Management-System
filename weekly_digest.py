"""Weekly email digest to info@growhivemedea.com."""
from __future__ import annotations

from datetime import date, timedelta

from email_service import NOTIFY_EMAIL, log_and_send
from helpers import cash_flow_forecast, company_financial_position, fetch_projects, kwacha


def build_weekly_digest_html(conn) -> str:
    projects = fetch_projects(conn)
    position = company_financial_position(conn)
    forecast = cash_flow_forecast(conn, projects)

    lead_count = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE status IN ('new','contacted','proposal')").fetchone()["c"]
    overdue_inv = conn.execute(
        """
        SELECT COUNT(*) AS c FROM invoices
        WHERE status IN ('unpaid','partial','overdue') AND due_date IS NOT NULL AND due_date < date('now')
        """
    ).fetchone()["c"]
    tax_due = conn.execute(
        "SELECT COUNT(*) AS c FROM tax_obligations WHERE status='pending' AND due_date <= date('now', '+30 days')"
    ).fetchone()["c"]
    hours_week = conn.execute(
        """
        SELECT COALESCE(SUM(hours), 0) AS h FROM time_entries
        WHERE entry_date >= date('now', '-7 days')
        """
    ).fetchone()["h"]

    still_collect = sum(p.get("remaining_balance", 0) for p in projects)
    mrr = sum(p.get("maintenance_amount", 0) for p in projects if p.get("has_monthly_maintenance") and p["status"] == "ongoing")

    rows = ""
    for pt in forecast["points"]:
        rows += f"<tr><td style='padding:6px;border:1px solid #e2e8f0;'>{pt['label']}</td>"
        rows += f"<td style='padding:6px;border:1px solid #e2e8f0;text-align:right;color:#059669;'>{kwacha(pt['inflows'])}</td>"
        rows += f"<td style='padding:6px;border:1px solid #e2e8f0;text-align:right;color:#dc2626;'>{kwacha(pt['outflows'])}</td>"
        rows += f"<td style='padding:6px;border:1px solid #e2e8f0;text-align:right;font-weight:bold;'>{kwacha(pt['balance'])}</td></tr>"

    return f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:640px;color:#0f172a;">
      <h2 style="color:#0f766e;margin:0 0 8px;">GrowHive Media — Weekly Digest</h2>
      <p style="color:#64748b;margin:0 0 16px;">Week ending {date.today().strftime('%d %b %Y')} · {NOTIFY_EMAIL}</p>

      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
        <tr><td style="padding:8px;background:#f0fdfa;"><b>Stanbic Balance</b></td><td style="padding:8px;text-align:right;">{kwacha(position['bank_balance'])}</td></tr>
        <tr><td style="padding:8px;"><b>Still to Collect</b></td><td style="padding:8px;text-align:right;">{kwacha(still_collect)}</td></tr>
        <tr><td style="padding:8px;background:#f0fdfa;"><b>Maintenance MRR</b></td><td style="padding:8px;text-align:right;">{kwacha(mrr)}</td></tr>
        <tr><td style="padding:8px;"><b>Active Leads</b></td><td style="padding:8px;text-align:right;">{lead_count}</td></tr>
        <tr><td style="padding:8px;background:#f0fdfa;"><b>Overdue Invoices</b></td><td style="padding:8px;text-align:right;">{overdue_inv}</td></tr>
        <tr><td style="padding:8px;"><b>Tax Due (30 days)</b></td><td style="padding:8px;text-align:right;">{tax_due}</td></tr>
        <tr><td style="padding:8px;background:#f0fdfa;"><b>Hours Logged (7 days)</b></td><td style="padding:8px;text-align:right;">{hours_week:.1f}h</td></tr>
      </table>

      <h3 style="color:#115e59;font-size:14px;">Cash Flow Forecast (90 days)</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
        <tr style="background:#0f766e;color:white;">
          <th style="padding:6px;text-align:left;">Period</th>
          <th style="padding:6px;text-align:right;">Inflows</th>
          <th style="padding:6px;text-align:right;">Outflows</th>
          <th style="padding:6px;text-align:right;">Balance</th>
        </tr>
        {rows}
      </table>
      <p style="font-size:11px;color:#94a3b8;">776 Mukuba Natwenge, Kitwe, Zambia · Automated weekly report</p>
    </div>
    """


def send_weekly_digest(conn) -> bool:
    html = build_weekly_digest_html(conn)
    return log_and_send(conn, f"Weekly Digest — {date.today().strftime('%d %b %Y')}", html, "weekly_digest")

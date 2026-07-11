from __future__ import annotations

import io
import os
from calendar import month_name

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from helpers import kwacha

LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "images", "growthhive-logo.jpg")

MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Heading1"], fontSize=18,
            textColor=colors.HexColor("#0f766e"), spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontSize=9,
            textColor=colors.HexColor("#64748b"), spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "Section", parent=base["Heading2"], fontSize=11,
            textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9, leading=12),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#94a3b8"), alignment=1,
        ),
    }


def _table_style(header: bool = False) -> TableStyle:
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    else:
        style.append(("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"))
        style.append(("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0fdfa")))
    return TableStyle(style)


def _kv_table(rows: list[list], col_widths=None) -> Table:
    t = Table(rows, colWidths=col_widths or [2.2 * inch, 3.8 * inch])
    t.setStyle(_table_style(header=False))
    return t


def _data_table(header: list, rows: list[list], col_widths=None) -> Table:
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(_table_style(header=True))
    return t


def _company_header(story, company: dict, report_title: str, period_label: str, styles: dict):
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        logo_cell = Image(LOGO_PATH, width=0.85 * inch, height=0.85 * inch)
    info = Paragraph(
        f"<b>{company['company_name']}</b><br/>"
        f"{company.get('tagline') or 'Technology & Marketing Solutions'}<br/>"
        f"<font size='7' color='#64748b'>"
        f"{company.get('email') or ''} · {company.get('phone') or ''}<br/>"
        f"{company.get('address') or ''}</font>",
        styles["body"],
    )
    header = Table([[logo_cell, info]], colWidths=[1.1 * inch, 4.9 * inch])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)
    story.append(Paragraph(report_title, styles["title"]))
    story.append(Paragraph(period_label, styles["subtitle"]))
    story.append(Spacer(1, 0.08 * inch))


def build_financial_report_pdf(
    company: dict,
    *,
    scope: str,
    year: int,
    month: int | None,
    month_data: dict | None,
    months: list[dict],
    payments: list,
    expenses: list,
    projects: list,
    position: dict,
    generated_by: str,
) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=48, leftMargin=48, topMargin=42, bottomMargin=42,
    )
    styles = _styles()
    story: list = []

    if scope == "month" and month:
        period = f"{month_name[month]} {year} · Zambian Kwacha (ZMW)"
        title = "Monthly Financial Report"
    else:
        period = f"Full Year {year} · Zambian Kwacha (ZMW)"
        title = "Annual Financial Report"

    _company_header(story, company, title, period, styles)

    if scope == "month" and month_data:
        summary = [
            ["Income Received (Projects)", kwacha(month_data["project_income"])],
            ["Project Expenses", kwacha(month_data["project_expenses"])],
            ["Project Profit", kwacha(month_data["project_profit"])],
            ["Investment Returns", kwacha(month_data["investment_profit"])],
            ["Total Revenue", kwacha(month_data["revenue"])],
            ["Company Expenses", kwacha(month_data["company_expenses"])],
            ["Net Profit", kwacha(month_data["profit"])],
            ["Profit Target", kwacha(month_data["profit_target"])],
            ["Revenue Target", kwacha(month_data["revenue_target"])],
        ]
        story.append(Paragraph("Financial Summary", styles["heading"]))
        story.append(_kv_table(summary))
        story.append(Spacer(1, 0.12 * inch))

        pos_rows = [
            ["Stanbic Bank Balance", kwacha(position["bank_balance"])],
            ["Company Reserves", kwacha(position["reserves"])],
            ["Total Available", kwacha(position["total_available"])],
        ]
        story.append(Paragraph("Company Position", styles["heading"]))
        story.append(_kv_table(pos_rows))
        story.append(Spacer(1, 0.12 * inch))

        if payments:
            story.append(Paragraph("Payments Received", styles["heading"]))
            pay_rows = [
                [p["payment_date"], p.get("project_name") or "—", p.get("description") or "—", kwacha(p["amount"])]
                for p in payments
            ]
            story.append(_data_table(
                ["Date", "Project", "Description", "Amount"],
                pay_rows,
                col_widths=[0.9 * inch, 1.5 * inch, 2.0 * inch, 1.1 * inch],
            ))
            story.append(Spacer(1, 0.1 * inch))

        if expenses:
            story.append(Paragraph("Expenses", styles["heading"]))
            exp_rows = [
                [
                    e["expense_date"],
                    e.get("category") or "—",
                    (e.get("project_name") or "Company")[:28],
                    e.get("description") or "—",
                    kwacha(e["amount"]),
                ]
                for e in expenses
            ]
            story.append(_data_table(
                ["Date", "Category", "Project", "Description", "Amount"],
                exp_rows,
                col_widths=[0.75 * inch, 0.85 * inch, 1.1 * inch, 1.5 * inch, 0.9 * inch],
            ))
            story.append(Spacer(1, 0.1 * inch))

        if projects:
            story.append(Paragraph("Active Projects This Month", styles["heading"]))
            proj_rows = [
                [
                    p["client_company"][:22],
                    p["name"][:24],
                    p["status"].title(),
                    kwacha(p.get("month_received", 0)),
                    kwacha(p.get("month_expenses", 0)),
                ]
                for p in projects
            ]
            story.append(_data_table(
                ["Client", "Project", "Status", "Received", "Expenses"],
                proj_rows,
                col_widths=[1.2 * inch, 1.4 * inch, 0.8 * inch, 1.0 * inch, 1.0 * inch],
            ))
    else:
        ytd_revenue = sum(m["revenue"] for m in months)
        ytd_profit = sum(m["profit"] for m in months)
        ytd_target = sum(m["profit_target"] for m in months)
        ytd_investment = sum(m["investment_profit"] for m in months)
        ytd_project_profit = sum(m["project_profit"] for m in months)
        ytd_project_income = sum(m["project_income"] for m in months)
        ytd_company_expenses = sum(m["company_expenses"] for m in months)

        story.append(Paragraph("Year-to-Date Summary", styles["heading"]))
        story.append(_kv_table([
            ["Total Revenue", kwacha(ytd_revenue)],
            ["Project Profit", kwacha(ytd_project_profit)],
            ["Income Received (Gross)", kwacha(ytd_project_income)],
            ["Investment Returns", kwacha(ytd_investment)],
            ["Company Expenses", kwacha(ytd_company_expenses)],
            ["Net Profit", kwacha(ytd_profit)],
            ["Profit Target (YTD)", kwacha(ytd_target)],
            ["Stanbic Bank Balance", kwacha(position["bank_balance"])],
            ["Company Reserves", kwacha(position["reserves"])],
        ]))
        story.append(Spacer(1, 0.12 * inch))

        story.append(Paragraph(f"Monthly Breakdown — {year}", styles["heading"]))
        month_rows = []
        for m in months:
            status = "On Target" if m["profit"] >= m["profit_target"] and m["profit_target"] > 0 else (
                "Below" if m["profit"] > 0 else "—"
            )
            month_rows.append([
                MONTH_SHORT[m["month"] - 1],
                kwacha(m["project_income"]),
                kwacha(m["project_profit"]),
                kwacha(m["investment_profit"]),
                kwacha(m["revenue"]),
                kwacha(m["company_expenses"]),
                kwacha(m["profit"]),
                kwacha(m["profit_target"]),
                status,
            ])
        story.append(_data_table(
            ["Month", "Income", "Proj. Profit", "Inv.", "Total Rev.", "Co. Exp.", "Net", "Target", "Status"],
            month_rows,
            col_widths=[0.5 * inch, 0.75 * inch, 0.65 * inch, 0.8 * inch, 0.75 * inch, 0.75 * inch, 0.75 * inch, 0.55 * inch],
        ))

    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(
        f"Generated by {generated_by} · {company['company_name']} · Confidential",
        styles["footer"],
    ))
    doc.build(story)
    buffer.seek(0)
    return buffer


def build_project_report_pdf(
    company: dict,
    project: dict,
    *,
    month_label: str,
    totals: dict,
    payments: list,
    expenses: list,
    subcontractors: list,
    position: dict,
    generated_by: str,
) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=42, bottomMargin=42)
    styles = _styles()
    story: list = []

    _company_header(
        story, company,
        "Monthly Project Report",
        f"{project['name']} — {month_label} (ZMW)",
        styles,
    )

    project_info = [
        ["Project", project["name"]],
        ["Client", project["client_company"]],
        ["Location", project.get("client_location") or project.get("client_address") or "—"],
        ["Email", project.get("client_email") or "—"],
        ["Website", project.get("client_website") or "—"],
        ["Phone", project.get("client_phone") or "—"],
        ["Status", project["status"].title()],
        ["Contract", kwacha(project["contract_amount"])],
        ["Payment Terms", project.get("payment_terms") or "—"],
    ]
    story.append(Paragraph("Project & Client Details", styles["heading"]))
    story.append(_kv_table(project_info))
    story.append(Spacer(1, 0.12 * inch))

    month_pay = sum(p["amount"] for p in payments)
    month_exp = sum(e["amount"] for e in expenses)
    summary = [
        ["Total Received (All Time)", kwacha(totals["received"])],
        ["Total Expenses (All Time)", kwacha(totals["expenses"])],
        ["Remaining Balance", kwacha(totals["remaining"])],
        ["Total Revenue (Profit)", kwacha(totals["total_revenue"])],
        [f"Payments — {month_label}", kwacha(month_pay)],
        [f"Expenses — {month_label}", kwacha(month_exp)],
        ["Stanbic Bank Balance", kwacha(position["bank_balance"])],
        ["Company Reserves", kwacha(position["reserves"])],
    ]
    story.append(Paragraph("Financial Summary", styles["heading"]))
    story.append(_kv_table(summary))
    story.append(Spacer(1, 0.12 * inch))

    if payments:
        story.append(Paragraph(f"Payments — {month_label}", styles["heading"]))
        story.append(_data_table(
            ["Date", "Description", "Amount"],
            [[p["payment_date"], p.get("description") or "—", kwacha(p["amount"])] for p in payments],
            col_widths=[1.2 * inch, 3.3 * inch, 1.0 * inch],
        ))
        story.append(Spacer(1, 0.1 * inch))

    if expenses:
        story.append(Paragraph(f"Expenses — {month_label}", styles["heading"]))
        story.append(_data_table(
            ["Date", "Category", "Description", "Amount"],
            [[e["expense_date"], e.get("category") or "—", e.get("description") or "—", kwacha(e["amount"])] for e in expenses],
            col_widths=[1.0 * inch, 1.0 * inch, 2.5 * inch, 1.0 * inch],
        ))
        story.append(Spacer(1, 0.1 * inch))

    if subcontractors:
        story.append(Paragraph("Subcontractors", styles["heading"]))
        story.append(_data_table(
            ["Name", "Company", "Contract", "Paid"],
            [[s["name"], s.get("company") or "—", kwacha(s["contract_amount"]), kwacha(s["amount_paid"])] for s in subcontractors],
            col_widths=[1.3 * inch, 1.5 * inch, 1.1 * inch, 1.1 * inch],
        ))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        f"Generated by {generated_by} · {company['company_name']} · Confidential",
        styles["footer"],
    ))
    doc.build(story)
    buffer.seek(0)
    return buffer

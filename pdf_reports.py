from __future__ import annotations

import io
import os
from calendar import month_name
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from company_defaults import DEFAULT_ADDRESS, DEFAULT_EMAIL, DEFAULT_PHONE
from helpers import kwacha

LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "images", "growthhive-logo.jpg")

MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BRAND = colors.HexColor("#0f766e")
BRAND_DARK = colors.HexColor("#115e59")
SLATE = colors.HexColor("#64748b")
BORDER = colors.HexColor("#e2e8f0")

PDF_MARGINS = dict(rightMargin=48, leftMargin=48, topMargin=42, bottomMargin=48)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Heading1"], fontSize=18,
            textColor=BRAND, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontSize=9,
            textColor=SLATE, spaceAfter=8,
        ),
        "heading": ParagraphStyle(
            "Section", parent=base["Heading2"], fontSize=11,
            textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9, leading=12),
        "small": ParagraphStyle("Small", parent=base["Normal"], fontSize=8, leading=11, textColor=SLATE),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#94a3b8"), alignment=1, spaceBefore=6,
        ),
    }


def company_contact_lines(company: dict) -> tuple[str, str, str]:
    email = company.get("email") or DEFAULT_EMAIL
    phone = company.get("phone") or DEFAULT_PHONE
    address = company.get("address") or DEFAULT_ADDRESS
    return email, phone, address


def _table_style(header: bool = False, kv: bool = False) -> TableStyle:
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    elif kv:
        style.extend([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0fdfa")),
        ])
    return TableStyle(style)


def _kv_table(rows: list[list], col_widths=None) -> Table:
    t = Table(rows, colWidths=col_widths or [2.2 * inch, 3.8 * inch])
    t.setStyle(_table_style(kv=True))
    return t


def _data_table(header: list, rows: list[list], col_widths=None) -> Table:
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(_table_style(header=True))
    return t


def _brand_bar(width=6 * inch) -> Table:
    bar = Table([[""]], colWidths=[width], rowHeights=[3])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    return bar


def _standard_header(story, company: dict, styles: dict, doc_type: str, doc_number: str = "", meta_lines: list[str] | None = None):
    email, phone, address = company_contact_lines(company)
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        logo_cell = Image(LOGO_PATH, width=0.8 * inch, height=0.8 * inch)

    company_block = Paragraph(
        f"<b>{company['company_name']}</b><br/>"
        f"{company.get('tagline') or 'Technology & Marketing Solutions'}<br/>"
        f"<font size='7' color='#64748b'>{address}<br/>"
        f"{email} · {phone}</font>",
        styles["body"],
    )
    meta = meta_lines or []
    meta_html = "<br/>".join(meta) if meta else ""
    doc_block = Paragraph(
        f"<b><font size='14' color='#115e59'>{doc_type.upper()}</font></b><br/>"
        f"<font size='8'>{doc_number}</font><br/>{meta_html}",
        ParagraphStyle("Meta", parent=styles["body"], alignment=2),
    )
    header = Table([[logo_cell, company_block, doc_block]], colWidths=[1.0 * inch, 3.2 * inch, 1.8 * inch])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header)
    story.append(_brand_bar())
    story.append(Spacer(1, 0.12 * inch))


def _standard_footer(story, company: dict, generated_by: str, styles: dict):
    email, phone, address = company_contact_lines(company)
    story.append(Spacer(1, 0.2 * inch))
    story.append(_brand_bar())
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph(
        f"<b>{company['company_name']}</b> · {address}<br/>"
        f"{email} · {phone} · All amounts in Zambian Kwacha (ZMW)",
        styles["footer"],
    ))
    story.append(Paragraph(
        f"Generated by {generated_by} · {datetime.now().strftime('%d %b %Y %H:%M')} · Confidential",
        styles["footer"],
    ))


def _company_header(story, company: dict, report_title: str, period_label: str, styles: dict):
    _standard_header(story, company, styles, report_title, meta_lines=[period_label, "Zambian Kwacha (ZMW)"])


def _bill_to_block(client: dict, styles: dict) -> Table:
    rows = [
        ["Bill To", client.get("client_company") or "—"],
        ["Contact", client.get("client_contact") or "—"],
        ["Email", client.get("client_email") or "—"],
        ["Phone", client.get("client_phone") or "—"],
        ["Address", client.get("client_address") or "—"],
    ]
    return _kv_table(rows)


def _line_items_table(items: list[dict]) -> Table:
    rows = [
        [
            item["description"],
            f"{item['quantity']:g}",
            kwacha(item["unit_price"]),
            kwacha(item["quantity"] * item["unit_price"]),
        ]
        for item in items
    ]
    return _data_table(
        ["Description", "Qty", "Unit Price", "Amount"],
        rows,
        col_widths=[3.0 * inch, 0.6 * inch, 1.1 * inch, 1.1 * inch],
    )


def _totals_block(subtotal: float, tax_rate: float, tax_amount: float, total: float, extra_rows: list | None = None) -> Table:
    rows = [["Subtotal", kwacha(subtotal)]]
    if tax_rate > 0:
        rows.append([f"Tax ({tax_rate:g}%)", kwacha(tax_amount)])
    rows.append(["Total", kwacha(total)])
    if extra_rows:
        rows.extend(extra_rows)
    t = Table(rows, colWidths=[4.2 * inch, 1.6 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), BRAND_DARK),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
    ]))
    return t


def _build_pdf(story_builders, company: dict, generated_by: str) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, **PDF_MARGINS)
    styles = _styles()
    story: list = []
    story_builders(story, styles)
    _standard_footer(story, company, generated_by, styles)
    doc.build(story)
    buffer.seek(0)
    return buffer


def build_quotation_pdf(company: dict, quote: dict, items: list[dict], generated_by: str) -> io.BytesIO:
    def build(story, styles):
        meta = [f"Date: {quote.get('created_at', '')[:10]}", f"Valid until: {quote.get('valid_until') or '—'}"]
        _standard_header(story, company, styles, "Quotation", quote["quote_number"], meta)
        story.append(Paragraph(quote.get("title") or "Quotation", styles["title"]))
        story.append(_bill_to_block(quote, styles))
        story.append(Spacer(1, 0.12 * inch))
        story.append(_line_items_table(items))
        story.append(Spacer(1, 0.1 * inch))
        story.append(_totals_block(quote["subtotal"], quote["tax_rate"], quote["tax_amount"], quote["total"]))
        if quote.get("notes"):
            story.append(Spacer(1, 0.12 * inch))
            story.append(Paragraph("Notes", styles["heading"]))
            story.append(Paragraph(quote["notes"], styles["body"]))
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(
            "Thank you for considering GrowthHive Media. We look forward to working with you.",
            styles["small"],
        ))
    return _build_pdf(build, company, generated_by)


def build_invoice_pdf(company: dict, invoice: dict, items: list[dict], generated_by: str) -> io.BytesIO:
    balance = invoice["total"] - invoice.get("amount_paid", 0)

    def build(story, styles):
        meta = [
            f"Date: {invoice.get('created_at', '')[:10]}",
            f"Due: {invoice.get('due_date') or '—'}",
            f"Status: {(invoice.get('status') or 'unpaid').replace('_', ' ').title()}",
        ]
        _standard_header(story, company, styles, "Invoice", invoice["invoice_number"], meta)
        story.append(Paragraph(invoice.get("title") or "Invoice", styles["title"]))
        story.append(_bill_to_block(invoice, styles))
        story.append(Spacer(1, 0.12 * inch))
        story.append(_line_items_table(items))
        story.append(Spacer(1, 0.1 * inch))
        extra = []
        if invoice.get("amount_paid", 0) > 0:
            extra.append(["Amount Paid", kwacha(invoice["amount_paid"])])
            extra.append(["Balance Due", kwacha(balance)])
        story.append(_totals_block(invoice["subtotal"], invoice["tax_rate"], invoice["tax_amount"], invoice["total"], extra))
        if invoice.get("notes"):
            story.append(Spacer(1, 0.12 * inch))
            story.append(Paragraph("Payment Instructions", styles["heading"]))
            story.append(Paragraph(
                invoice["notes"] + "<br/><br/>Pay via Stanbic Bank Zambia — contact us for account details.",
                styles["body"],
            ))
    return _build_pdf(build, company, generated_by)


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
    def build(story, styles):
        if scope == "month" and month:
            period = f"{month_name[month]} {year}"
            doc_no = f"FIN-{year}-{month:02d}"
        else:
            period = f"Full Year {year}"
            doc_no = f"FIN-{year}"

        _standard_header(story, company, styles, "Financial Report", doc_no, [period, "Zambian Kwacha (ZMW)"])

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
                        e["expense_date"], e.get("category") or "—",
                        (e.get("project_name") or "Company")[:28],
                        e.get("description") or "—", kwacha(e["amount"]),
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
                        p["client_company"][:22], p["name"][:24], p["status"].title(),
                        kwacha(p.get("month_received", 0)), kwacha(p.get("month_expenses", 0)),
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

    return _build_pdf(build, company, generated_by)


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
    def build(story, styles):
        doc_no = f"PRJ-{project['id']}-{month_label.replace(' ', '-')}"
        _standard_header(story, company, styles, "Project Report", doc_no, [project["name"], month_label])

        project_info = [
            ["Project", project["name"]],
            ["Client", project["client_company"]],
            ["Location", project.get("client_location") or project.get("client_address") or "—"],
            ["Email", project.get("client_email") or "—"],
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
            ["Income Received", kwacha(totals["received"])],
            ["Total Expenses", kwacha(totals["expenses"])],
            ["Still to Collect", kwacha(totals["remaining"])],
            ["Total Revenue (Profit)", kwacha(totals["total_revenue"])],
            [f"Payments — {month_label}", kwacha(month_pay)],
            [f"Expenses — {month_label}", kwacha(month_exp)],
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

    return _build_pdf(build, company, generated_by)

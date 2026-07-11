from __future__ import annotations

import io
import os
from calendar import month_name
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from company_defaults import DEFAULT_ADDRESS, DEFAULT_EMAIL, DEFAULT_PHONE
from helpers import kwacha

LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "images", "growthhive-logo.jpg")

MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BRAND = colors.HexColor("#0f766e")
BRAND_DARK = colors.HexColor("#115e59")
SLATE = colors.HexColor("#64748b")
BORDER = colors.HexColor("#e2e8f0")

# Dark Blue Yellow Professional Construct Invoice template
DOC_NAVY = colors.HexColor("#2d3743")
DOC_GOLD = colors.HexColor("#ffbd59")

PDF_MARGINS = dict(rightMargin=48, leftMargin=48, topMargin=42, bottomMargin=48)
PAGE_W, PAGE_H = A4


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


def _pretty_doc_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %B, %Y")
    except ValueError:
        return value[:10]


def _zmw_amount(value: float) -> str:
    """Line-item and total amounts in Kwacha (replaces $ in reference template)."""
    return f"K {value:,.2f}"


def _draw_terms_block(c, terms: str, x: float, y_top: float) -> None:
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawString(x, y_top, "Thank You For Your Business")
    c.drawString(x, y_top - 14, "TERMS")
    c.setFont("Helvetica", 10)
    y = y_top - 28
    for line in terms.splitlines():
        line = line.strip()
        if line:
            c.drawString(x, y, line[:72])
            y -= 13


def _draw_commercial_document(
    c: canvas.Canvas,
    *,
    company: dict,
    doc_title: str,
    doc_number: str,
    record: dict,
    items: list[dict],
    generated_by: str,
    date_label: str,
    due_label: str,
    due_value: str | None,
) -> None:
    """Layout based on Dark Blue Yellow Professional Construct Invoice.pdf."""
    email, phone, address = company_contact_lines(company)
    client_name = record.get("client_contact") or record.get("client_contact_name") or "—"

    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Top navy header
    c.setFillColor(DOC_NAVY)
    c.rect(-10, PAGE_H - 260, PAGE_W + 20, 260, fill=1, stroke=0)

    # Logo (top-left, unchanged asset)
    if os.path.exists(LOGO_PATH):
        c.drawImage(LOGO_PATH, 75, PAGE_H - 130, width=60, height=58, preserveAspectRatio=True, mask="auto")

    # Bill-to panel (gold labels, white values)
    rx, ty = 365, PAGE_H - 76
    for label, value in (
        ("To:", client_name),
        ("Company :", record.get("client_company") or "—"),
        ("Mail :", record.get("client_email") or "—"),
    ):
        c.setFillColor(DOC_GOLD)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(rx, ty, label)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 11)
        c.drawString(rx + 68, ty, str(value)[:42])
        ty -= 48

    # Yellow vertical bar + rotated document title
    c.setFillColor(DOC_GOLD)
    c.rect(59, PAGE_H - 521, 99, 322, fill=1, stroke=0)
    c.saveState()
    c.setFillColor(DOC_NAVY)
    c.setFont("Helvetica-Bold", 46)
    c.translate(108, PAGE_H - 360)
    c.rotate(90)
    c.drawCentredString(0, -16, doc_title)
    c.restoreState()

    # Table header band
    table_top = PAGE_H - 260
    table_h = 52
    c.setFillColor(DOC_GOLD)
    c.rect(211, table_top - table_h, 394, table_h, fill=1, stroke=0)
    c.setFillColor(DOC_NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(249, table_top - 32, "DESC")
    c.drawString(424, table_top - 32, "PRICE")
    c.drawString(360, table_top - 32, "QTY")
    c.drawString(495, table_top - 32, "TOTAL")

    # Line items
    row_y = table_top - table_h - 18
    row_step = 44
    c.setFont("Helvetica", 11)
    c.setFillColor(DOC_NAVY)
    for item in items:
        qty = float(item["quantity"])
        price = float(item["unit_price"])
        line_total = qty * price
        c.drawString(249, row_y, str(item["description"])[:36])
        c.drawRightString(464, row_y, _zmw_amount(price))
        c.drawCentredString(372, row_y, f"{qty:g}")
        c.drawRightString(540, row_y, _zmw_amount(line_total))
        row_y -= row_step
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.setLineWidth(0.5)
        c.line(213, row_y + 32, 553, row_y + 32)

    # Subtotal / tax (if applicable)
    subtotal = float(record.get("subtotal") or 0)
    tax_rate = float(record.get("tax_rate") or 0)
    tax_amount = float(record.get("tax_amount") or 0)
    grand_total = float(record.get("total") or 0)
    if tax_rate > 0:
        row_y -= 8
        c.setFont("Helvetica", 10)
        c.drawString(396, row_y, "Subtotal")
        c.drawRightString(576, row_y, _zmw_amount(subtotal))
        row_y -= 16
        c.drawString(396, row_y, f"Tax ({tax_rate:g}%)")
        c.drawRightString(576, row_y, _zmw_amount(tax_amount))

    # Grand total
    row_y -= 24
    c.setFont("Helvetica-Bold", 13)
    c.drawString(396, row_y, "TOTAL")
    c.drawRightString(576, row_y, f"ZMW {grand_total:,.2f}")

    if record.get("amount_paid", 0) > 0:
        row_y -= 18
        c.setFont("Helvetica", 10)
        paid = float(record["amount_paid"])
        c.drawRightString(
            576, row_y,
            f"Paid: {_zmw_amount(paid)}   Balance: {_zmw_amount(grand_total - paid)}",
        )

    # Terms block
    default_terms = (
        "60% of payment is required before the start of any work\n"
        "40% upon completing the work"
    )
    terms = (record.get("notes") or "").strip() or default_terms
    _draw_terms_block(c, terms, 60, 250)

    # Yellow meta band (invoice / quote details)
    c.setFillColor(DOC_GOLD)
    c.rect(59, 111, 323, 64, fill=1, stroke=0)
    c.setFillColor(DOC_NAVY)
    c.setFont("Helvetica-Bold", 11)
    number_label = "Invoice No :" if doc_title == "INVOICE" else "Quote No :"
    c.drawString(75, 163, number_label)
    c.drawString(174, 163, date_label)
    c.drawString(289, 163, due_label)
    c.setFont("Helvetica", 11)
    c.drawString(75, 139, doc_number)
    c.drawString(174, 139, _pretty_doc_date(record.get("created_at")))
    c.drawString(289, 139, _pretty_doc_date(due_value))

    # Sales Manager (label fixed; name = document author)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(412, 152, "Sales Manager")
    c.setFont("Helvetica", 10)
    c.drawCentredString(464, 135, generated_by[:28])

    # Footer bar — company phone, address, email
    c.setFillColor(DOC_NAVY)
    c.rect(-10, 0, PAGE_W + 20, 73, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 9)
    c.drawString(99, 46, phone)
    c.drawRightString(496, 46, address)
    c.drawCentredString(PAGE_W / 2, 32, email)


def _commercial_pdf(
    company: dict,
    doc_title: str,
    doc_number: str,
    record: dict,
    items: list[dict],
    generated_by: str,
    date_label: str,
    due_label: str,
    due_value: str | None,
) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _draw_commercial_document(
        c,
        company=company,
        doc_title=doc_title,
        doc_number=doc_number,
        record=record,
        items=items,
        generated_by=generated_by,
        date_label=date_label,
        due_label=due_label,
        due_value=due_value,
    )
    c.save()
    buffer.seek(0)
    return buffer


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
    return _commercial_pdf(
        company,
        "QUOTATION",
        quote["quote_number"],
        quote,
        items,
        generated_by,
        date_label="Quote Date :",
        due_label="Valid Until :",
        due_value=quote.get("valid_until"),
    )


def build_invoice_pdf(company: dict, invoice: dict, items: list[dict], generated_by: str) -> io.BytesIO:
    return _commercial_pdf(
        company,
        "INVOICE",
        invoice["invoice_number"],
        invoice,
        items,
        generated_by,
        date_label="Invoice Date :",
        due_label="Due Date :",
        due_value=invoice.get("due_date"),
    )


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

from __future__ import annotations

import json
from datetime import datetime

from helpers import log_audit


def create_approval(conn, user, action_type: str, payload: dict, entity_type: str = "", entity_id: int | None = None):
    from permissions import approval_summary

    summary = approval_summary(action_type, payload)
    conn.execute(
        """
        INSERT INTO pending_approvals
        (requested_by, requested_by_name, action_type, entity_type, entity_id, payload, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            user["name"],
            action_type,
            entity_type,
            entity_id,
            json.dumps(payload),
            summary,
        ),
    )
    log_audit(conn, user, f"Submitted for approval: {summary}", "approval", entity_id, action_type)


def execute_approval(conn, approval) -> None:
    payload = json.loads(approval["payload"])
    action = approval["action_type"]
    project_id = approval["entity_id"] or payload.get("project_id")

    if action == "add_payment":
        conn.execute(
            "INSERT INTO payments_received (project_id, amount, description, payment_date) VALUES (?, ?, ?, ?)",
            (project_id, payload["amount"], payload.get("description", ""), payload["payment_date"]),
        )
    elif action == "add_expense":
        conn.execute(
            "INSERT INTO expenses (project_id, amount, description, category, expense_date) VALUES (?, ?, ?, ?, ?)",
            (
                payload.get("project_id"),
                payload["amount"],
                payload["description"],
                payload.get("category", ""),
                payload["expense_date"],
            ),
        )
    elif action == "add_subcontractor":
        conn.execute(
            """
            INSERT INTO subcontractors
            (project_id, name, company, contact_email, contact_phone, contract_amount, amount_paid, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                payload["name"],
                payload.get("company", ""),
                payload.get("contact_email", ""),
                payload.get("contact_phone", ""),
                payload["contract_amount"],
                payload.get("amount_paid", 0),
                payload.get("notes", ""),
            ),
        )
    elif action == "edit_project_contract":
        conn.execute(
            """
            UPDATE projects SET contract_amount=?, payment_terms=?, updated_at=datetime('now') WHERE id=?
            """,
            (payload["contract_amount"], payload.get("payment_terms", ""), project_id),
        )

    if project_id:
        conn.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?", (project_id,))


def review_approval(conn, approval_id: int, admin_user, approve: bool, note: str = "") -> bool:
    row = conn.execute(
        "SELECT * FROM pending_approvals WHERE id=? AND status='pending'", (approval_id,)
    ).fetchone()
    if not row:
        return False
    if approve:
        execute_approval(conn, row)
        status = "approved"
    else:
        status = "rejected"
    conn.execute(
        """
        UPDATE pending_approvals SET
            status=?, reviewed_by=?, reviewed_by_name=?, review_note=?, reviewed_at=datetime('now')
        WHERE id=?
        """,
        (status, admin_user["id"], admin_user["name"], note, approval_id),
    )
    log_audit(
        conn, admin_user,
        f"{'Approved' if approve else 'Rejected'}: {row['summary']}",
        "approval", approval_id, note,
    )
    return True

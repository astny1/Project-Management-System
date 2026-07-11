from __future__ import annotations

ROLE_LABELS = {
    "admin": "Admin",
    "sales_manager": "Sales Manager",
    "project_manager": "Project Manager",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "sales_manager": {
        "dashboard", "clients", "clients_view", "projects_view", "projects_create",
        "projects_edit", "reports", "finances_view", "accounting_view",
        "expenses_view", "reserves_view", "project_payments_request",
        "project_expenses_request", "leads_view", "documents_view",
    },
    "project_manager": {
        "dashboard", "clients_view", "projects_view", "maintenance_view",
        "reports", "project_expenses_request", "subcontractors_request",
        "operations_view", "documents_view",
    },
}

NAV_BY_ROLE: dict[str, list[tuple[str, str]]] = {
    "admin": [
        ("dashboard", "Dashboard"),
        ("clients", "Clients"),
        ("maintenance", "Maintenance"),
        ("accounting", "Accounting"),
        ("reserves", "Reserves"),
        ("investments", "Investments"),
        ("company_expenses", "Expenses"),
        ("approvals", "Approvals"),
        ("team", "Team"),
        ("auditing", "Auditing"),
    ],
    "sales_manager": [
        ("dashboard", "Dashboard"),
        ("clients", "Clients"),
        ("reserves", "Reserves"),
        ("accounting", "Finances"),
        ("company_expenses", "Expenses"),
    ],
    "project_manager": [
        ("dashboard", "Dashboard"),
        ("maintenance", "Maintenance"),
        ("clients", "Clients"),
    ],
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").title())


def can(role: str | None, permission: str) -> bool:
    if not role:
        return False
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


NAV_GROUPS_BY_ROLE: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {
    "admin": [
        ("", [("dashboard", "Dashboard")]),
        ("Business", [("clients", "Clients"), ("leads", "Leads"), ("maintenance", "Maintenance")]),
        ("Finance", [
            ("accounting", "Accounting"), ("reserves", "Reserves"),
            ("investments", "Investments"), ("company_expenses", "Expenses"),
        ]),
        ("Management", [
            ("approvals", "Approvals"), ("team", "Team"),
            ("auditing", "Auditing"),
        ]),
    ],
    "sales_manager": [
        ("", [("dashboard", "Dashboard")]),
        ("Sales", [
            ("clients", "Clients"), ("leads", "Leads"), ("reserves", "Reserves"),
            ("accounting", "Finances"), ("company_expenses", "Expenses"),
        ]),
    ],
    "project_manager": [
        ("", [("dashboard", "Dashboard")]),
        ("Operations", [("maintenance", "Maintenance"), ("clients", "Clients")]),
    ],
}


def nav_items(role: str | None) -> list[tuple[str, str]]:
    if not role:
        return []
    return NAV_BY_ROLE.get(role, NAV_BY_ROLE["project_manager"])


def nav_groups(role: str | None) -> list[tuple[str, list[tuple[str, str]]]]:
    if not role:
        return []
    return NAV_GROUPS_BY_ROLE.get(role, NAV_GROUPS_BY_ROLE["project_manager"])


def requires_approval(role: str | None) -> bool:
    return role in ("sales_manager", "project_manager")


def approval_summary(action_type: str, data: dict) -> str:
    if action_type == "add_payment":
        return f"Payment K {float(data.get('amount', 0)):,.2f} — {data.get('description', 'Project payment')}"
    if action_type == "add_expense":
        return f"Expense K {float(data.get('amount', 0)):,.2f} — {data.get('description', '')}"
    if action_type == "add_subcontractor":
        return f"Subcontractor {data.get('name', '')} — K {float(data.get('contract_amount', 0)):,.2f}"
    if action_type == "edit_project_contract":
        return f"Contract update to K {float(data.get('contract_amount', 0)):,.2f} — {data.get('name', '')}"
    return action_type.replace("_", " ").title()

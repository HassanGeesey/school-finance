"""Expenses routes end-to-end: page, record form, category management modal.

Route-level smoke tests of the thin adapters + templates. Business rules
(category uniqueness, archiving, amount/date/method validation, audit content)
live in ``test_expenses_service.py``. Any logged-in user — including a Finance
officer — may record an expense and view the list; category management is
Admin-only and asserted here.
"""

import json
from typing import cast

from fastapi import FastAPI

from app.audit.service import AuditActions
from app.models import AuditLogEntry, Expense, ExpenseCategory

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def _db(client):
    return cast(FastAPI, client.app).state.db


def categories(client) -> list[ExpenseCategory]:
    with _db(client).session() as session:
        return session.query(ExpenseCategory).order_by(ExpenseCategory.id).all()


def expenses(client) -> list[Expense]:
    with _db(client).session() as session:
        return session.query(Expense).order_by(Expense.id).all()


def audit_entries(client, action):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def add_category(client, name, **overrides):
    data = {"name": name, **overrides}
    return client.post(
        "/expenses/categories",
        data=data,
        headers={"HX-Request": "true"},
    )


def record_expense(client, category_id, description="Bus fuel", amount="45.00",
                   method="cash", occurred_on="2026-08-06", **overrides):
    data = {
        "category_id": str(category_id),
        "description": description,
        "amount": amount,
        "method": method,
        "occurred_on": occurred_on,
        **overrides,
    }
    return client.post(
        "/expenses",
        data=data,
        headers={"HX-Request": "true"},
    )


# ---------------------------------------------------------------------------
# Login & role gating
# ---------------------------------------------------------------------------


def test_expenses_page_requires_login(client):
    setup_admin(client)

    response = client.get("/expenses", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_record_expense_requires_login(client):
    setup_admin(client)

    response = client.post("/expenses", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_category_management_requires_admin(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    created = categories(client)[0]

    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/expenses/categories",
        data={"name": "Salaries"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 403

    rename = client.post(
        f"/expenses/categories/{created.id}/rename",
        data={"name": "Renamed"},
        headers={"HX-Request": "true"},
    )
    assert rename.status_code == 403

    remove = client.post(
        f"/expenses/categories/{created.id}/remove",
        headers={"HX-Request": "true"},
    )
    assert remove.status_code == 403


# ---------------------------------------------------------------------------
# Category management (admin)
# ---------------------------------------------------------------------------


def test_admin_can_add_a_category(client):
    authenticated_admin(client)

    response = add_category(client, "Utilities")

    assert response.status_code == 200
    assert "Utilities" in response.text
    assert "toast" in response.headers["HX-Trigger"]
    assert len(categories(client)) == 1
    assert len(audit_entries(client, AuditActions.EXPENSE_CATEGORY_ADD)) == 1


def test_a_duplicate_category_name_shows_an_error(client):
    authenticated_admin(client)
    add_category(client, "Utilities")

    response = add_category(client, "Utilities")

    assert response.status_code == 200
    assert "already exists" in response.text
    assert len(categories(client)) == 1


def test_admin_can_rename_a_category(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    created = categories(client)[0]

    response = client.post(
        f"/expenses/categories/{created.id}/rename",
        data={"name": "Water & Power"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Water &amp; Power" in response.text
    assert len(audit_entries(client, AuditActions.EXPENSE_CATEGORY_RENAME)) == 1


def test_admin_can_remove_a_category(client):
    authenticated_admin(client)
    add_category(client, "Transport")
    created = categories(client)[0]

    response = client.post(
        f"/expenses/categories/{created.id}/remove",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert len(audit_entries(client, AuditActions.EXPENSE_CATEGORY_REMOVE)) == 1
    archived = categories(client)[0]
    assert archived.is_active is False


def test_only_admins_see_the_manage_categories_button(client):
    authenticated_admin(client)

    page = client.get("/expenses")
    assert 'id="categories-modal"' in page.text

    add_finance_user(client)
    login_finance(client)
    page = client.get("/expenses")
    assert 'id="categories-modal"' not in page.text


# ---------------------------------------------------------------------------
# Recording expenses
# ---------------------------------------------------------------------------


def test_finance_can_record_an_expense(client):
    authenticated_admin(client)
    add_category(client, "Transport")
    category_id = categories(client)[0].id
    add_finance_user(client)
    login_finance(client)

    response = record_expense(client, category_id, description="Bus fuel", amount="45.00")

    assert response.status_code == 200
    assert "Bus fuel" in response.text
    assert "$45.00" in response.text
    assert "toast" in response.headers["HX-Trigger"]
    (expense,) = expenses(client)
    assert expense.amount_cents == 4500
    assert expense.method == "cash"
    assert expense.description == "Bus fuel"
    assert len(audit_entries(client, AuditActions.EXPENSE_RECORD)) == 1


def test_a_new_category_appears_in_the_record_dropdown_after_adding(client):
    authenticated_admin(client)
    add_category(client, "Salaries")

    page = client.get("/expenses")

    assert "Salaries" in page.text
    assert 'name="category_id"' in page.text


def test_recording_an_expense_requires_a_category(client):
    authenticated_admin(client)

    response = record_expense(client, category_id=0)

    assert response.status_code == 200
    assert "category" in response.text.lower()
    assert expenses(client) == []
    assert audit_entries(client, AuditActions.EXPENSE_RECORD) == []


def test_an_invalid_amount_is_refused_with_no_expense_saved(client):
    authenticated_admin(client)
    add_category(client, "Supplies")
    category_id = categories(client)[0].id

    response = record_expense(client, category_id, amount="0")

    assert response.status_code == 200
    assert "greater than zero" in response.text
    assert expenses(client) == []
    assert audit_entries(client, AuditActions.EXPENSE_RECORD) == []


def test_a_future_expense_date_is_refused(client):
    authenticated_admin(client)
    add_category(client, "Supplies")
    category_id = categories(client)[0].id

    response = record_expense(client, category_id, occurred_on="2100-01-01")

    assert response.status_code == 200
    assert "cannot be in the future" in response.text
    assert expenses(client) == []


def test_recording_without_htmx_redirects_with_a_message(client):
    authenticated_admin(client)
    add_category(client, "Supplies")
    category_id = categories(client)[0].id

    response = client.post(
        "/expenses",
        data={
            "category_id": str(category_id),
            "description": "Pens",
            "amount": "5.00",
            "method": "cash",
            "occurred_on": "2026-08-06",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/expenses?msg=" in response.headers["location"]
    assert len(expenses(client)) == 1


# ---------------------------------------------------------------------------
# Expense list
# ---------------------------------------------------------------------------


def test_expenses_page_lists_expenses_with_a_total(client):
    authenticated_admin(client)
    add_category(client, "Transport")
    category_id = categories(client)[0].id
    record_expense(client, category_id, description="Bus fuel", amount="45.00")
    record_expense(client, category_id, description="Van fuel", amount="20.00", occurred_on="2026-08-05")

    page = client.get("/expenses")

    assert page.status_code == 200
    assert "Bus fuel" in page.text
    assert "Van fuel" in page.text
    assert "$65.00" in page.text  # filtered total
    assert "No expenses yet" not in page.text


def test_expenses_page_shows_an_empty_state(client):
    authenticated_admin(client)
    add_category(client, "Transport")

    page = client.get("/expenses")

    assert "No expenses yet" in page.text


def test_expenses_page_filters_by_category_and_month(client):
    authenticated_admin(client)
    add_category(client, "Supplies")
    add_category(client, "Salaries")
    supplies, salaries = categories(client)
    record_expense(client, supplies.id, description="Chalk", amount="10.00")
    record_expense(client, salaries.id, description="August pay", amount="500.00", occurred_on="2026-08-01")
    record_expense(client, supplies.id, description="Old chalk", amount="7.00", occurred_on="2026-07-15")

    page = client.get(f"/expenses?category={supplies.id}&period=2026-08")

    assert "Chalk" in page.text
    assert "Old chalk" not in page.text
    assert "August pay" not in page.text
    assert "$10.00" in page.text


def test_expenses_page_offers_month_filter_options(client):
    authenticated_admin(client)
    add_category(client, "Supplies")
    category_id = categories(client)[0].id
    record_expense(client, category_id, occurred_on="2026-08-06")

    page = client.get("/expenses")

    assert "August 2026" in page.text


def test_dashboard_partial_shows_the_form_once_a_category_exists(client):
    authenticated_admin(client)

    before = client.get("/expenses/dashboard")
    assert "No expense categories yet" in before.text
    assert 'name="category_id"' not in before.text

    add_category(client, "Stationery")

    after = client.get("/expenses/dashboard")
    assert "No expense categories yet" not in after.text
    assert 'name="category_id"' in after.text
    assert "Stationery" in after.text

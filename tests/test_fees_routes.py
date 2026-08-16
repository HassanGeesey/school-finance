"""Fee template routes: the Admin's templates page and its HTMX partials.

Thin adapters over :class:`app.fees.service.TemplateService`. Viewing is open to
any logged-in user; creating/editing/archiving is Admin-only (Q24). HTMX saves
return a fresh form plus an ``HX-Trigger`` (toast + ``templates-changed``); plain
requests get a 303 redirect. Service rules live in ``test_fees_service.py``.
"""

import json

import pytest

from app.models import FeeTemplate
from tests.helpers import in_admin_scope


def authenticated_mini_client(mini_client):
    from tests.helpers import authenticated_admin

    authenticated_admin(mini_client)
    return mini_client


def login_finance_client(mini_client):
    from tests.helpers import add_finance_user, login_finance

    add_finance_user(mini_client)
    login_finance(mini_client)
    return mini_client


def create_template(client, name="Standard", amount="100.00"):
    from tests.helpers import in_admin_scope

    service = client.app.state.fees
    return in_admin_scope(
        client, lambda: service.create_template(user=None, name=name, amount=amount)
    )


def add_closed_month(client, month=7, year=2026):
    from tests.helpers import in_admin_scope

    service = client.app.state.fees_closed
    return in_admin_scope(
        client, lambda: service.add_closed_month(user=None, month=month, year=year)
    )


def htmx_headers() -> dict[str, str]:
    return {"HX-Request": "true"}


# ---------------------------------------------------------------------------
# Viewing
# ---------------------------------------------------------------------------


def test_fees_page_requires_login(mini_client):
    response = mini_client.get("/fees", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_fees_page_lists_templates(mini_client):
    client = authenticated_mini_client(mini_client)
    create_template(client, name="Standard", amount="50.00")
    create_template(client, name="Boarding", amount="12.50")

    response = client.get("/fees")

    assert response.status_code == 200
    body = response.text
    assert "Standard" in body
    assert "Boarding" in body
    assert "$50.00" in body


def test_fees_page_is_open_to_finance(mini_client):
    client = login_finance_client(mini_client)
    create_template(client, name="Standard")

    response = client.get("/fees")

    assert response.status_code == 200
    assert "Standard" in response.text


def test_fees_page_shows_the_new_template_action_to_admin_only(mini_client):
    client = authenticated_mini_client(mini_client)
    admin_body = client.get("/fees").text
    login_finance_client(client)
    finance_body = client.get("/fees").text

    assert "/fees/templates/new-form" in admin_body
    assert "/fees/templates/new-form" not in finance_body


def test_templates_list_partial_renders_rows(mini_client):
    client = authenticated_mini_client(mini_client)
    create_template(client, name="Standard")

    response = client.get("/fees/templates/list")

    assert response.status_code == 200
    assert "Standard" in response.text
    assert "No fee templates yet" not in response.text


def test_templates_list_partial_shows_the_empty_state(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.get("/fees/templates/list")

    assert response.status_code == 200
    assert "No fee templates yet" in response.text


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_new_template_form_is_admin_only(mini_client):
    client = login_finance_client(mini_client)

    assert client.get("/fees/templates/new-form").status_code == 403


def test_new_template_form_renders(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.get("/fees/templates/new-form")

    assert response.status_code == 200
    assert "Create template" in response.text


def test_create_template_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/templates",
        data={"name": "Standard", "amount": "50.00"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "Fee template created."
    assert trigger["templates-changed"] is True
    assert client.app.state.db.session().query(FeeTemplate).one().amount_cents == 5000


def test_create_template_via_plain_redirect(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/templates",
        data={"name": "Standard", "amount": "50.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/fees")
    assert "msg=" in response.headers["location"]


def test_create_template_requires_admin(mini_client):
    client = login_finance_client(mini_client)

    response = client.post("/fees/templates", data={"name": "Standard", "amount": "50.00"})

    assert response.status_code == 403


def test_create_template_with_invalid_amount_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/templates",
        data={"name": "Standard", "amount": "0"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert "Enter a valid amount" not in response.text
    assert "Amount must be greater than zero" in response.text
    assert client.app.state.db.session().query(FeeTemplate).count() == 0


def test_create_template_with_invalid_amount_via_plain_redirect(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/templates",
        data={"name": "Standard", "amount": "0"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "err=" in response.headers["location"]


# ---------------------------------------------------------------------------
# Edit (effective-dated amount change)
# ---------------------------------------------------------------------------


def test_edit_template_form_is_admin_only(mini_client):
    client = login_finance_client(mini_client)

    assert client.get("/fees/templates/1/edit-form").status_code == 403


def test_edit_template_form_prefills_amount(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Standard", amount="55.50")

    response = client.get(f"/fees/templates/{template.id}/edit-form")

    assert response.status_code == 200
    assert "Standard" in response.text
    assert 'value="55.50"' in response.text


def test_edit_template_form_missing_template_404s(mini_client):
    client = authenticated_mini_client(mini_client)

    assert client.get("/fees/templates/999/edit-form").status_code == 404


def test_edit_template_amount_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Standard", amount="100.00")
    from app.fees.service import default_effective_month

    month, year = default_effective_month()

    response = client.post(
        f"/fees/templates/{template.id}/edit",
        data={"name": "Standard", "amount": "120.00", "month": str(month), "year": str(year)},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["templates-changed"] is True
    with client.app.state.db.session() as session:
        assert session.get(FeeTemplate, template.id).amount_cents == 12000


def test_edit_template_rename_only_via_plain_redirect(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Standard", amount="100.00")

    response = client.post(
        f"/fees/templates/{template.id}/edit",
        data={"name": "Premium", "amount": "100.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with client.app.state.db.session() as session:
        assert session.get(FeeTemplate, template.id).name == "Premium"


def test_edit_template_rejects_a_past_effective_month(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Standard", amount="100.00")
    from datetime import date

    today = date.today()
    past_year, past_month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)

    response = client.post(
        f"/fees/templates/{template.id}/edit",
        data={"name": "Standard", "amount": "120.00", "month": str(past_month), "year": str(past_year)},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert "past" in response.text


def test_edit_template_missing_template_404s(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/templates/999/edit",
        data={"name": "Standard", "amount": "120.00"},
        headers=htmx_headers(),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Archive / restore
# ---------------------------------------------------------------------------


def test_archive_template_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client)

    response = client.post(
        f"/fees/templates/{template.id}/archive", headers=htmx_headers()
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "Fee template archived."
    with client.app.state.db.session() as session:
        assert session.get(FeeTemplate, template.id).archived is True


def test_archive_then_restore_template(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client)
    client.post(f"/fees/templates/{template.id}/archive", headers=htmx_headers())

    response = client.post(
        f"/fees/templates/{template.id}/restore", headers=htmx_headers()
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "Fee template restored."
    with client.app.state.db.session() as session:
        assert session.get(FeeTemplate, template.id).archived is False


def test_archive_template_requires_admin(mini_client):
    client = login_finance_client(mini_client)

    assert client.post("/fees/templates/1/archive").status_code == 403
    assert client.post("/fees/templates/1/restore").status_code == 403


def test_archive_missing_template_404s(mini_client):
    client = authenticated_mini_client(mini_client)

    assert client.post("/fees/templates/999/archive").status_code == 404


# ---------------------------------------------------------------------------
# Closed months (FW-17): the Admin's school-wide closed-month list
# ---------------------------------------------------------------------------


def test_fees_page_shows_the_closed_months_section(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.get("/fees")

    assert response.status_code == 200
    assert "Closed months" in response.text


def test_closed_months_list_partial_renders_rows(mini_client):
    client = authenticated_mini_client(mini_client)
    add_closed_month(client, month=7, year=2026)

    response = client.get("/fees/closed-months/list")

    assert response.status_code == 200
    assert "July 2026" in response.text
    assert "No closed months" not in response.text


def test_closed_months_list_partial_shows_the_empty_state(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.get("/fees/closed-months/list")

    assert response.status_code == 200
    assert "No closed months" in response.text


def test_closed_months_list_is_open_to_finance(mini_client):
    client = login_finance_client(mini_client)

    assert client.get("/fees/closed-months/list").status_code == 200


def test_closed_months_add_form_is_admin_only(mini_client):
    client = login_finance_client(mini_client)

    body = client.get("/fees/closed-months/list").text

    assert "Close month" not in body
    assert "/fees/closed-months" not in body


def test_add_closed_month_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/closed-months",
        data={"month": "7", "year": "2026"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "July 2026 closed."
    assert in_admin_scope(client, client.app.state.fees_closed.closed_month_set) == {(7, 2026)}


def test_add_closed_month_via_plain_redirect(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/closed-months",
        data={"month": "7", "year": "2026"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/fees")
    assert "msg=" in response.headers["location"]


def test_add_closed_month_requires_admin(mini_client):
    client = login_finance_client(mini_client)

    response = client.post(
        "/fees/closed-months", data={"month": "7", "year": "2026"}
    )

    assert response.status_code == 403


def test_add_duplicate_closed_month_shows_an_error(mini_client):
    client = authenticated_mini_client(mini_client)
    add_closed_month(client, month=7, year=2026)

    response = client.post(
        "/fees/closed-months",
        data={"month": "7", "year": "2026"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert "already closed" in response.text
    assert in_admin_scope(client, client.app.state.fees_closed.closed_month_set) == {(7, 2026)}


def test_add_closed_month_rejects_an_invalid_period(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/closed-months",
        data={"month": "13", "year": "2026"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert "between 1 and 12" in response.text


def test_remove_closed_month_via_htmx(mini_client):
    client = authenticated_mini_client(mini_client)
    add_closed_month(client, month=7, year=2026)

    response = client.post(
        "/fees/closed-months/remove",
        data={"month": "7", "year": "2026"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "July 2026 reopened."
    assert in_admin_scope(client, client.app.state.fees_closed.closed_month_set) == set()


def test_remove_closed_month_that_is_not_closed_shows_an_error(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/fees/closed-months/remove",
        data={"month": "7", "year": "2026"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert "not on the closed list" in response.text


def test_remove_closed_month_requires_admin(mini_client):
    client = login_finance_client(mini_client)

    response = client.post(
        "/fees/closed-months/remove", data={"month": "7", "year": "2026"}
    )

    assert response.status_code == 403

"""Fee template routes: the Admin's templates page and its HTMX partials.

Thin adapters over :class:`app.fees.service.TemplateService`. Viewing is open to
any logged-in user; creating/editing/archiving is Admin-only (Q24). HTMX saves
return a fresh form plus an ``HX-Trigger`` (toast + ``templates-changed``); plain
requests get a 303 redirect. Service rules live in ``test_fees_service.py``.
"""

import json

import pytest

from app.models import FeeTemplate


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
    service = client.app.state.fees
    return service.create_template(user=None, name=name, amount=amount)


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

"""Waiver routes: the account page's add-waiver modal and its htmx partials.

Thin adapters over :class:`app.fees.service.WaiverService`. The form is loaded
into the account page's modal (month picker prefilled with an owed month) and
posts over htmx — a save returns a fresh form plus a toast and a
``waivers-changed`` event (which closes the modal and refreshes the account
finance body); plain requests get a 303 redirect. Both Admin and Finance officer
can waive (FW-13), so these routes are behind ``require_login`` only. Service
rules live in ``test_waivers_service.py``.
"""

import json
from urllib.parse import urlparse

from app.fees.service import period_label
from app.models import Waiver

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def htmx_headers() -> dict[str, str]:
    return {"HX-Request": "true"}


def create_class(client, name="Grade 1", status="active"):
    response = client.post(
        "/classes",
        data={"name": name, "status": status},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def add_student(client, class_id=1, first_name="Ada", last_name="Lovelace"):
    return client.post(
        f"/classes/{class_id}/students",
        data={
            "first_name": first_name,
            "last_name": last_name,
            "enrolled_on": "2026-03-01",
            "fee_template_id": "",
            "custom_amount": "50.00",
        },
        follow_redirects=False,
    )


def make_billed_student(client, first_name="Ada", last_name="Lovelace"):
    class_id = create_class(client)
    response = add_student(client, class_id, first_name=first_name, last_name=last_name)
    assert response.status_code == 303
    from app.models import Student

    with client.app.state.db.session() as session:
        return session.query(Student).one().id


def waiver_count(client) -> int:
    with client.app.state.db.session() as session:
        return session.query(Waiver).count()


# ---------------------------------------------------------------------------
# The form
# ---------------------------------------------------------------------------


def test_waiver_form_requires_login(client):
    setup_admin(client)

    response = client.get("/students/1/waivers/new-form", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_waiver_form_renders_with_owed_months(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.get(f"/students/{student_id}/waivers/new-form")

    assert response.status_code == 200
    assert "Add waiver" in response.text
    # The month picker lists an owed month and prefills the oldest unpaid one.
    assert period_label(3, 2026) in response.text
    assert 'value="2026-03"' in response.text


def test_waiver_form_is_open_to_finance(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get(f"/students/{student_id}/waivers/new-form")

    assert response.status_code == 200


def test_waiver_form_unknown_student_404s(client):
    authenticated_admin(client)

    assert client.get("/students/999/waivers/new-form").status_code == 404


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_add_waiver_via_htmx(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "10.00", "label": "Skipped week"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["toast"]["message"] == "Waiver added."
    assert trigger["waivers-changed"] is True
    assert waiver_count(client) == 1


def test_add_waiver_via_plain_redirect(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "10.00", "label": "Skipped week"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/students/{student_id}/account")
    assert "msg=" in response.headers["location"]
    assert waiver_count(client) == 1


def test_finance_officer_can_add_a_waiver(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "50.00", "label": "Left early"},
        headers=htmx_headers(),
    )

    assert response.status_code == 200
    assert waiver_count(client) == 1
    with client.app.state.db.session() as session:
        waiver = session.query(Waiver).one()
        assert waiver.label == "Left early"
        assert waiver.created_by is not None


def test_add_waiver_requires_a_reason(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "10.00", "label": ""},
        headers=htmx_headers(),
    )

    assert response.status_code == 400
    assert "reason" in response.text.lower()
    assert waiver_count(client) == 0


def test_add_waiver_rejects_an_invalid_amount(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "0", "label": "Discount"},
        headers=htmx_headers(),
    )

    assert response.status_code == 400
    assert "greater than zero" in response.text
    assert waiver_count(client) == 0


def test_add_waiver_rejects_an_invalid_period(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)

    response = client.post(
        f"/students/{student_id}/waivers",
        data={"period": "not-a-month", "amount": "10.00", "label": "Discount"},
        headers=htmx_headers(),
    )

    assert response.status_code == 400
    assert waiver_count(client) == 0


def test_add_waiver_unknown_student_404s(client):
    authenticated_admin(client)

    response = client.post(
        "/students/999/waivers",
        data={"period": "2026-04", "amount": "10.00", "label": "Discount"},
    )

    assert response.status_code == 404
    assert waiver_count(client) == 0


# ---------------------------------------------------------------------------
# Account page history
# ---------------------------------------------------------------------------


def test_account_page_shows_waiver_history(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)
    client.post(
        f"/students/{student_id}/waivers",
        data={"period": "2026-04", "amount": "10.00", "label": "Skipped week"},
    )

    response = client.get(f"/students/{student_id}/account")

    assert response.status_code == 200
    assert "Skipped week" in response.text
    assert "$10.00" in response.text
    assert "$40.00" in response.text  # $50 expected − $10 waived for April


def test_account_page_shows_the_add_waiver_action_to_finance(client):
    authenticated_admin(client)
    student_id = make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get(f"/students/{student_id}/account")

    assert response.status_code == 200
    assert "/waivers/new-form" in response.text

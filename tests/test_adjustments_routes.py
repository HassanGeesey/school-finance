"""Adjustments routes end-to-end: student account, adjust modal, and the POST.

Route-level smoke tests of the thin adapters + templates. Business rules
(waiver cap, audit content, live balance) live in ``test_adjustments_service.py``.
Role gating — Finance officers may view but never adjust — is asserted here.
"""

from typing import cast
from urllib.parse import urlparse

from fastapi import FastAPI

from app.audit.service import AuditActions
from app.models import Adjustment, AuditLogEntry, Charge

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def create_class(client, name="Grade 1", status="active"):
    response = client.post(
        "/classes",
        data={"name": name, "status": status},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def add_fee_item(client, class_id, name="Tuition", amount="50.00"):
    response = client.post(
        f"/classes/{class_id}/fee-items",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )
    assert response.status_code == 303


def add_student(client, class_id, first_name="Ada", last_name="Lovelace"):
    response = client.post(
        f"/classes/{class_id}/students",
        data={"first_name": first_name, "last_name": last_name},
        follow_redirects=False,
    )
    assert response.status_code == 303


def generate_fees(client, class_id):
    response = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200


def _db(client):
    return cast(FastAPI, client.app).state.db


def student_and_charge_ids(client):
    with _db(client).session() as session:
        charge = session.query(Charge).one()
        return charge.student_id, charge.id


def adjustments(client):
    with _db(client).session() as session:
        return session.query(Adjustment).all()


def audit_entries(client, action=AuditActions.ADJUSTMENT_ADD):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def make_billed_student(client):
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)
    generate_fees(client, class_id)
    return student_and_charge_ids(client)


# ---------------------------------------------------------------------------
# Account page
# ---------------------------------------------------------------------------


def test_account_page_requires_login(client):
    setup_admin(client)

    response = client.get("/students/1/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_account_page_404s_for_a_missing_student(client):
    authenticated_admin(client)

    response = client.get("/students/999/account")
    assert response.status_code == 404


def test_admin_can_open_the_account_page(client):
    authenticated_admin(client)
    student_id, _ = make_billed_student(client)

    response = client.get(f"/students/{student_id}/account")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Balance owed" in response.text
    assert "$50.00" in response.text
    assert "March 2026" in response.text
    assert "Adjust" in response.text


def test_account_page_shows_an_empty_state_without_charges(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_student(client, class_id)
    with _db(client).session() as session:
        from app.models import Student

        student_id = session.query(Student).one().id

    response = client.get(f"/students/{student_id}/account")

    assert response.status_code == 200
    assert "No charges yet" in response.text
    assert "$0.00" in response.text


def test_finance_officer_can_view_but_not_adjust(client):
    authenticated_admin(client)
    student_id, charge_id = make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get(f"/students/{student_id}/account")
    assert response.status_code == 200
    assert "Balance owed" in response.text
    assert ">Adjust<" not in response.text
    assert "adjust-form" not in response.text

    denied = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "extra", "label": "Lunch", "amount": "2.00"},
        headers={"HX-Request": "true"},
    )
    assert denied.status_code == 403
    assert adjustments(client) == []

    denied_form = client.get(f"/charges/{charge_id}/adjust-form")
    assert denied_form.status_code == 403


# ---------------------------------------------------------------------------
# Adjust form (modal)
# ---------------------------------------------------------------------------


def test_adjust_form_shows_the_charge_context(client):
    authenticated_admin(client)
    _, charge_id = make_billed_student(client)

    response = client.get(f"/charges/{charge_id}/adjust-form")

    assert response.status_code == 200
    assert "Adjust March 2026 charge" in response.text
    assert "Extra" in response.text
    assert "Waiver" in response.text
    assert "Save adjustment" in response.text
    assert "$50.00" in response.text


def test_adjust_form_404s_for_a_missing_charge(client):
    authenticated_admin(client)

    response = client.get("/charges/999/adjust-form")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Making an adjustment
# ---------------------------------------------------------------------------


def test_admin_can_add_an_extra(client):
    authenticated_admin(client)
    student_id, charge_id = make_billed_student(client)

    response = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "extra", "label": "Lunch", "amount": "3.50"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#account-finance"
    assert "Added extra" in response.headers["HX-Trigger"]
    assert "Lunch" in response.text
    assert "$3.50" in response.text
    assert "$53.50" in response.text  # balance + net cell

    page = client.get(f"/students/{student_id}/account")
    assert "Extra" in page.text
    assert "Lunch" in page.text
    assert len(audit_entries(client)) == 1


def test_admin_can_apply_a_waiver(client):
    authenticated_admin(client)
    student_id, charge_id = make_billed_student(client)

    response = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "waiver", "label": "Scholarship", "amount": "10.00"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Applied waiver" in response.headers["HX-Trigger"]
    assert "$10.00" in response.text
    assert "$40.00" in response.text

    page = client.get(f"/students/{student_id}/account")
    assert "Scholarship" in page.text
    assert len(audit_entries(client)) == 1


def test_an_excessive_waiver_is_refused_in_the_modal(client):
    authenticated_admin(client)
    _, charge_id = make_billed_student(client)

    response = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "waiver", "label": "Too much", "amount": "70.00"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "below zero" in response.text
    assert "HX-Retarget" not in response.headers
    assert adjustments(client) == []
    assert audit_entries(client) == []


def test_an_invalid_kind_is_refused(client):
    authenticated_admin(client)
    _, charge_id = make_billed_student(client)

    response = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "discount", "label": "Whatever", "amount": "5.00"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Choose Extra or Waiver." in response.text
    assert adjustments(client) == []


def test_a_non_htmx_adjust_redirects_with_a_message(client):
    authenticated_admin(client)
    student_id, charge_id = make_billed_student(client)

    response = client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "extra", "label": "Lunch", "amount": "2.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/students/{student_id}/account?msg=")

    page = client.get(response.headers["location"])
    assert "Added extra" in page.text
    assert len(audit_entries(client)) == 1


def test_adjustment_appears_in_the_audit_log(client):
    authenticated_admin(client)
    student_id, charge_id = make_billed_student(client)

    client.post(
        f"/charges/{charge_id}/adjust",
        data={"kind": "extra", "label": "Lunch", "amount": "3.50"},
        headers={"HX-Request": "true"},
    )

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Adjustment made" in response.text
    assert "Ada Lovelace" in response.text
    assert "March 2026" in response.text
    assert "$3.50" in response.text
    assert student_id  # keep linters happy

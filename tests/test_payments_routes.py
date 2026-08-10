"""Payments routes end-to-end: index, record form, the POST, and the receipt.

Route-level smoke tests of the thin adapters + templates. Business rules
(oldest-first allocation, credits, audit content, live balance) live in
``test_payments_service.py``. Any logged-in user — including a Finance officer —
may view and record payments; role gating is asserted here.
"""

from datetime import date
from typing import cast
from urllib.parse import urlparse

from fastapi import FastAPI

from app.audit.service import AuditActions
from app.fees.service import period_label
from app.models import AuditLogEntry, Credit, FeeTemplate, Payment, Student

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def _db(client):
    return cast(FastAPI, client.app).state.db


def add_fee_template(client, name="Tuition", amount="50.00"):
    response = client.post(
        "/fees/templates",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with _db(client).session() as session:
        return session.query(FeeTemplate).filter_by(name=name).one().id


def create_class(client, name="Grade 1", status="active", template_id=None):
    data = {"name": name, "status": status}
    if template_id is not None:
        data["default_template_id"] = str(template_id)
    response = client.post(
        "/classes",
        data=data,
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def add_student(client, class_id, first_name="Ada", last_name="Lovelace"):
    response = client.post(
        f"/classes/{class_id}/students",
        data={"first_name": first_name, "last_name": last_name},
        follow_redirects=False,
    )
    assert response.status_code == 303


def student_id(client):
    with _db(client).session() as session:
        return session.query(Student).one().id


def make_billed_student(client, amount="50.00"):
    """A student who owes the current month's fee (enrolled today)."""
    template_id = add_fee_template(client, amount=amount)
    class_id = create_class(client, template_id=template_id)
    add_student(client, class_id)
    return student_id(client)


def payments(client):
    with _db(client).session() as session:
        return session.query(Payment).order_by(Payment.id).all()


def credits(client):
    with _db(client).session() as session:
        return session.query(Credit).all()


def audit_entries(client, action=AuditActions.PAYMENT_RECORD):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


# ---------------------------------------------------------------------------
# Payments index
# ---------------------------------------------------------------------------


def test_payments_page_requires_login(client):
    setup_admin(client)

    response = client.get("/payments", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_payments_page_starts_without_a_selected_student(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/payments")

    assert response.status_code == 200
    assert "No student selected" in response.text
    assert "Save &amp; print receipt" in response.text


def test_payments_search_dropdown_lists_matching_students(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/payments/student-picker?q=Ada")
    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "$50.00" in response.text
    assert "Owes $50.00" in response.text

    response = client.get("/payments/student-picker?q=Grace")
    assert "No students found" in response.text


def test_selecting_a_student_swaps_in_their_summary(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.get(f"/payments/student-picker/select?student_id={sid}")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "$50.00" in response.text
    assert "Owes $50.00" in response.text
    assert f'name="student_id" value="{sid}"' in response.text


# ---------------------------------------------------------------------------
# Record form
# ---------------------------------------------------------------------------


def test_record_form_requires_login(client):
    setup_admin(client)

    response = client.get("/payments/record?student_id=1", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_record_form_404s_for_a_missing_student(client):
    authenticated_admin(client)

    response = client.get("/payments/record?student_id=999")
    assert response.status_code == 404


def test_record_form_shows_the_student_balance(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.get(f"/payments/record?student_id={sid}")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "$50.00" in response.text
    assert "Record payment" in response.text


def test_payment_preview_shows_the_allocation_without_writing(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.get(f"/payments/preview?student_id={sid}&amount=60.00")

    assert response.status_code == 200
    assert period_label(date.today().month, date.today().year) in response.text
    assert "$50.00" in response.text
    assert "Credit on account" in response.text
    assert "$10.00" in response.text
    with _db(client).session() as session:
        assert session.query(Payment).count() == 0


def test_payment_preview_shows_an_error_for_an_invalid_amount(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.get(f"/payments/preview?student_id={sid}&amount=0")

    assert response.status_code == 200
    assert "greater than zero" in response.text


# ---------------------------------------------------------------------------
# Recording a payment
# ---------------------------------------------------------------------------


def test_admin_can_record_a_payment_and_land_on_the_receipt(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "30.00", "method": "cash", "paid_on": "2026-08-06"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert "/receipt?msg=" in location

    receipt = client.get(location)
    assert receipt.status_code == 200
    assert "Receipt #1" in receipt.text
    assert "Ada Lovelace" in receipt.text
    assert "$30.00" in receipt.text
    assert period_label(date.today().month, date.today().year) in receipt.text
    assert "Print" in receipt.text

    (payment,) = payments(client)
    assert payment.amount_cents == 3000
    assert len(audit_entries(client)) == 1
    assert credits(client) == []


def test_an_overpayment_becomes_credit_and_shows_on_the_receipt(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "60.00", "method": "cash", "paid_on": "2026-08-06"},
        follow_redirects=False,
    )

    receipt = client.get(response.headers["location"])
    assert "Credit on account" in receipt.text
    assert "$10.00" in receipt.text
    (credit,) = credits(client)
    assert credit.amount_cents == 1000


def test_a_partial_payment_reduces_the_balance_on_the_account_page(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "30.00", "method": "cash", "paid_on": "2026-08-06"},
        follow_redirects=False,
    )

    page = client.get(f"/students/{sid}/account")
    assert page.status_code == 200
    assert "$20.00" in page.text  # remaining balance
    assert "Partial" in page.text
    assert "Cash" in page.text
    assert "Receipt" in page.text


def test_an_invalid_amount_is_refused_with_no_payment_saved(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "0", "method": "cash", "paid_on": "2026-08-06"},
    )

    assert response.status_code == 400
    assert "greater than zero" in response.text
    assert payments(client) == []
    assert audit_entries(client) == []


def test_a_future_payment_date_is_refused(client):
    authenticated_admin(client)
    sid = make_billed_student(client)

    response = client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "10.00", "method": "cash", "paid_on": "2100-01-01"},
    )

    assert response.status_code == 400
    assert "cannot be in the future" in response.text
    assert payments(client) == []


def test_a_finance_officer_can_record_a_payment(client):
    authenticated_admin(client)
    sid = make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    page = client.get(f"/payments/record?student_id={sid}")
    assert page.status_code == 200

    response = client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "10.00", "method": "bank", "paid_on": "2026-08-06"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(payments(client)) == 1
    assert len(audit_entries(client)) == 1


def test_a_recorded_payment_reduces_the_balance_on_the_payments_page(client):
    authenticated_admin(client)
    sid = make_billed_student(client)
    client.post(
        "/payments/record",
        data={"student_id": str(sid), "amount": "10.00", "method": "cash", "paid_on": "2026-08-06"},
        follow_redirects=False,
    )

    page = client.get("/payments")
    assert page.status_code == 200
    assert "Cash" in page.text  # method options still listed

    response = client.get(f"/payments/student-picker/select?student_id={sid}")
    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "$40.00" in response.text  # $50 owed minus the $10 payment


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------


def test_receipt_requires_login(client):
    setup_admin(client)

    response = client.get("/payments/1/receipt", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_receipt_404s_for_a_missing_payment(client):
    authenticated_admin(client)

    response = client.get("/payments/999/receipt")
    assert response.status_code == 404

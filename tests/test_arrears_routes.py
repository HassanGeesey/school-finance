"""Arrears routes end-to-end: the outstanding-money report page.

Route-level smoke tests of the thin adapter + template. Business rules (what
counts as arrears, debt-age bands, who is included) live in
``test_arrears_service.py``. Any logged-in user — including a Finance officer —
may view the report; role gating is asserted here.
"""

from datetime import date
from typing import cast
from urllib.parse import urlparse

from fastapi import FastAPI

from app.fees.service import period_label
from app.models import FeeTemplate

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
        return (
            session.query(FeeTemplate)
            .filter_by(name=name)
            .order_by(FeeTemplate.id.desc())
            .first()
            .id
        )


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


def record_payment(client, student_id, amount):
    response = client.post(
        "/payments/record",
        data={
            "student_id": str(student_id),
            "amount": amount,
            "method": "cash",
            "paid_on": date.today().isoformat(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def make_billed_student(client, name="Grade 1", first_name="Ada", last_name="Lovelace", status="active"):
    template_id = add_fee_template(client)
    class_id = create_class(client, name=name, status=status, template_id=template_id)
    add_student(client, class_id, first_name=first_name, last_name=last_name)
    return class_id


def student_ids(client):
    from app.models import Student

    with _db(client).session() as session:
        return {student.full_name: student.id for student in session.query(Student).all()}


# ---------------------------------------------------------------------------
# Login / role gating
# ---------------------------------------------------------------------------


def test_arrears_page_requires_login(client):
    setup_admin(client)

    response = client.get("/arrears", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_a_finance_officer_can_view_the_report(client):
    authenticated_admin(client)
    make_billed_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text


# ---------------------------------------------------------------------------
# Report content
# ---------------------------------------------------------------------------


def test_report_lists_owing_students_with_amount_and_age(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" in response.text
    assert "$50.00" in response.text  # each owes the current month's fee
    assert period_label(date.today().month, date.today().year) in response.text  # oldest unpaid month
    assert "0-30 days" in response.text  # current-month debt
    assert "2" in response.text  # owing-students stat


def test_report_shows_the_sidebar_nav_item_active(client):
    authenticated_admin(client)

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "/arrears" in response.text
    assert "Unpaid fees" in response.text


def test_fully_paid_students_are_excluded(client):
    authenticated_admin(client)
    class_id = make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "50.00")

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "Ada Lovelace" not in response.text
    assert "No unpaid fees" in response.text


def test_a_partial_payment_reduces_the_reported_amount(client):
    authenticated_admin(client)
    make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "30.00")

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "$20.00" in response.text  # 50.00 charge minus 30.00 paid


def test_archived_students_and_completed_classes_still_appear(client):
    authenticated_admin(client)
    # A student in a completed class still owes their billed months.
    make_billed_student(client, name="Grade 8", status="completed")

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Completed" in response.text  # class status badge


def test_empty_state_when_nobody_owes(client):
    authenticated_admin(client)
    make_billed_student(client)
    record_payment(client, student_ids(client)["Ada Lovelace"], "50.00")

    response = client.get("/arrears")

    assert response.status_code == 200
    assert "No unpaid fees" in response.text
    assert "nothing outstanding" in response.text

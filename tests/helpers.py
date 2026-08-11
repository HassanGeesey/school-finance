"""Shared helpers for route-level smoke tests and billing fixtures.

The setup/login flows are identical across feature route tests and the
derived-billing factory helpers are reused by the account/arrears/reports
service tests; keeping them in one place stops each feature module from
duplicating them.
"""

from datetime import date
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.service import hash_password
from app.models import (
    Class,
    ClassStatus,
    Credit,
    FeeTemplate,
    Payment,
    Student,
    StudentAmountChange,
    StudentStatus,
    User,
    UserRoles,
)

NAME = "Head Teacher"
USERNAME = "admin"
PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"


def setup_admin(client: TestClient) -> None:
    response = client.post(
        "/setup",
        data={
            "school_name": SCHOOL_NAME,
            "name": NAME,
            "username": USERNAME,
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def login(client: TestClient, username: str = USERNAME, password: str = PASSWORD) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def authenticated_admin(client: TestClient) -> None:
    setup_admin(client)
    login(client)


def add_finance_user(client: TestClient) -> None:
    with cast(FastAPI, client.app).state.db.session() as session:
        session.add(
            User(
                name="Cashier",
                username="cashier",
                password_hash=hash_password("long enough password"),
                role=UserRoles.FINANCE,
            )
        )
        session.commit()


def login_finance(client: TestClient) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, username="cashier", password="long enough password")


# -- Derived-billing fixtures (ticket 07/08 service tests) ---------------------


def make_billed_student(
    session,
    *,
    enrolled_on,
    archived_on=None,
    amount=5000,
    first="Ada",
    last="Lovelace",
    class_name="Grade 1",
    class_status=ClassStatus.ACTIVE,
    status=StudentStatus.ACTIVE,
) -> Student:
    """A student linked to a fee template, so every owed month expects ``amount``."""
    cls = Class(name=class_name, status=class_status)
    session.add(cls)
    session.flush()
    template = FeeTemplate(name="Standard", amount_cents=amount)
    session.add(template)
    session.flush()
    student = Student(
        class_id=cls.id,
        first_name=first,
        last_name=last,
        status=status,
        enrolled_on=enrolled_on,
        archived_on=archived_on,
        fee_template_id=template.id,
    )
    session.add(student)
    session.flush()
    # The students service seeds the amount in force at the enrollment month
    # (``_seed_amount``); mirror it so past months resolve without a template
    # lazy-load.
    session.add(
        StudentAmountChange(
            student_id=student.id,
            amount_cents=amount,
            month=enrolled_on.month,
            year=enrolled_on.year,
        )
    )
    session.flush()
    return student


def add_payment(session, student_id, amount_cents, month, year, paid_on=None) -> Payment:
    payment = Payment(
        student_id=student_id,
        amount_cents=amount_cents,
        method="cash",
        paid_on=paid_on or date(year, month, 1),
        month=month,
        year=year,
    )
    session.add(payment)
    session.flush()
    return payment


def add_credit(session, student_id, amount_cents, payment=None) -> Credit:
    credit = Credit(
        student_id=student_id,
        amount_cents=amount_cents,
        payment_id=payment.id if payment is not None else None,
    )
    session.add(credit)
    session.flush()
    return credit

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
    Campus,
    Class,
    ClassStatus,
    Credit,
    FeeTemplate,
    Payment,
    School,
    Student,
    StudentAmountChange,
    StudentStatus,
    User,
    UserRoles,
)
from app.tenants.scope import scope

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
        school = session.query(School).one()
        campus = session.query(Campus).filter_by(school_id=school.id).first()
        session.add(
            User(
                name="Cashier",
                username="cashier",
                password_hash=hash_password("long enough password"),
                role=UserRoles.FINANCE,
                school_id=school.id,
                campus_id=campus.id if campus is not None else None,
            )
        )
        session.commit()


def login_finance(client: TestClient) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, username="cashier", password="long enough password")


def login_as(
    client: TestClient, username: str, password: str = "long enough password"
) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, username=username, password=password)


def in_admin_scope(client: TestClient, fn):
    """Run ``fn`` under the implicit school's Admin scope.

    Route tests seed data by calling a service directly (``app.state.<service>``),
    which runs outside an HTTP request and so has no request scope. The tenant
    layer (ticket 09) makes unscoped service calls an error, so seeding is
    wrapped in the acting Admin's scope (falling back to any user in
    finance-only tests).
    """
    from app.models import User
    from app.tenants.scope import RequestScope, scope_context

    with cast(FastAPI, client.app).state.db.session() as session:
        user = (
            session.query(User).filter_by(username=USERNAME).one_or_none()
            or session.query(User).order_by(User.id).first()
        )
    with scope_context(RequestScope.for_user(user)):
        return fn()


def seed_second_campus(client: TestClient) -> tuple[int, int]:
    """A second Campus of the implicit School, its Admin, and a Superadmin.

    Returns ``(campus_b_id, superadmin_user_id)``. The School is the one the
    offline setup already bootstrapped; the second Campus's Admin and the
    School-bound Superadmin are created ready to log in.
    """
    with cast(FastAPI, client.app).state.db.session() as session:
        school = session.query(School).one()
        campus_b = Campus(school_id=school.id, name="Campus B")
        session.add(campus_b)
        session.flush()
        admin_b = User(
            name="Admin B",
            username="admin_b",
            password_hash=hash_password("long enough password"),
            role=UserRoles.ADMIN,
            school_id=school.id,
            campus_id=campus_b.id,
        )
        superadmin = User(
            name="Super",
            username="super",
            password_hash=hash_password("long enough password"),
            role=UserRoles.SUPERADMIN,
            school_id=school.id,
        )
        session.add_all([admin_b, superadmin])
        session.commit()
        return campus_b.id, superadmin.id


# -- Derived-billing fixtures (ticket 07/08 service tests) ---------------------


def _campus_id() -> int:
    """The acting scope's Campus: operational rows must carry one (ticket 09)."""
    campus_id = scope().campus_id if scope() is not None else None
    if campus_id is None:
        raise RuntimeError("billing fixtures require a campus-scoped context")
    return campus_id


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
    campus_id = _campus_id()
    cls = Class(name=class_name, status=class_status, campus_id=campus_id)
    session.add(cls)
    session.flush()
    template = FeeTemplate(name="Standard", amount_cents=amount, campus_id=campus_id)
    session.add(template)
    session.flush()
    student = Student(
        class_id=cls.id,
        campus_id=campus_id,
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
            campus_id=campus_id,
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
        campus_id=_campus_id(),
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
        campus_id=_campus_id(),
        amount_cents=amount_cents,
        payment_id=payment.id if payment is not None else None,
    )
    session.add(credit)
    session.flush()
    return credit

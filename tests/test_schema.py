"""Schema foundation: tables are created on startup, amounts stay as cents, and
the fee-billing reshape is reflected (no charge rows — enrollment-derived model).
"""

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Class,
    ClosedMonth,
    FeeTemplate,
    Payment,
    Student,
    User,
    Waiver,
)

EXPECTED_TABLES = {
    "users",
    "sessions",
    "classes",
    "students",
    "fee_templates",
    "waivers",
    "closed_months",
    "payments",
    "credits",
    "expense_categories",
    "expenses",
    "audit_log",
    "school_profile",
}

REMOVED_TABLES = {
    "fee_items",
    "charges",
    "adjustments",
    "payment_allocations",
    "generation_records",
}


def _make_class(db) -> Class:
    with db.session() as session:
        school_class = Class(name="Grade 3")
        session.add(school_class)
        session.commit()
        session.refresh(school_class)
        return school_class


def _make_student(db, session: Session) -> Student:
    school_class = _make_class(db)
    student = Student(class_id=school_class.id, first_name="Ada", last_name="Lovelace")
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def test_create_all_creates_every_domain_table(db):
    tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert REMOVED_TABLES.isdisjoint(tables)


def test_money_is_stored_as_integer_cents(db, session: Session):
    template = FeeTemplate(name="Standard", amount_cents=10000)
    session.add(template)
    session.commit()

    stored = session.query(FeeTemplate).one()
    assert stored.amount_cents == 10000
    assert isinstance(stored.amount_cents, int)


def test_student_defaults_enrolled_today_with_no_archive(db, session: Session):
    student = _make_student(db, session)

    assert student.enrolled_on == date.today()
    assert student.archived_on is None


def test_payment_requires_a_month_and_year_tag(db, session: Session):
    student = _make_student(db, session)

    with pytest.raises(IntegrityError):
        session.add(
            Payment(
                student_id=student.id,
                amount_cents=5000,
                method="cash",
                paid_on=date(2026, 3, 5),
            )
        )
        session.commit()


def test_payment_stores_the_month_tag(db, session: Session):
    student = _make_student(db, session)
    payment = Payment(
        student_id=student.id,
        amount_cents=5000,
        method="cash",
        paid_on=date(2026, 3, 5),
        month=3,
        year=2026,
    )
    session.add(payment)
    session.commit()

    stored = session.query(Payment).one()
    assert (stored.month, stored.year) == (3, 2026)


def test_waiver_is_unique_per_student_month_year(db, session: Session):
    student = _make_student(db, session)

    session.add(
        Waiver(
            student_id=student.id,
            month=3,
            year=2026,
            amount_cents=2000,
            label="Hardship",
        )
    )
    session.commit()

    with pytest.raises(IntegrityError):
        session.add(
            Waiver(
                student_id=student.id,
                month=3,
                year=2026,
                amount_cents=500,
                label="Another reason",
            )
        )
        session.commit()


def test_waiver_allows_stacking_on_different_months(db, session: Session):
    student = _make_student(db, session)
    for month in (3, 4):
        session.add(
            Waiver(
                student_id=student.id,
                month=month,
                year=2026,
                amount_cents=1000,
                label="Hardship",
            )
        )
    session.commit()

    assert session.query(Waiver).count() == 2


def test_closed_month_is_unique_per_month_year(db, session: Session):
    session.add(ClosedMonth(month=7, year=2026))
    session.commit()

    with pytest.raises(IntegrityError):
        session.add(ClosedMonth(month=7, year=2026))
        session.commit()


def test_round_trip_user_and_class(db, session: Session):
    session.add(User(username="admin", name="Head Teacher", password_hash="x", role="admin"))
    session.add(Class(name="Grade 3", status="active"))
    session.commit()

    assert session.query(User).count() == 1
    assert session.query(Class).one().name == "Grade 3"

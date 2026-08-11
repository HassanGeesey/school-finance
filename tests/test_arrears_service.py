"""Arrears service: the derived outstanding-money report (ticket 08).

Business rules only — the single testing seam. Arrears are the accumulated
monthly shortfalls across owed months (``expected - paid - credit``, positive
only); fully-paid, fully-credit-covered, and never-owed students are excluded.
Debt age is measured from the oldest owed month still carrying a shortfall and
banded current/late/overdue at 30/60 days; the report is oldest-debt-first.
Route concerns live in ``test_arrears_routes.py``.
"""

from datetime import date

import pytest

from app.arrears.service import (
    AGE_BAND_CURRENT,
    AGE_BAND_LATE,
    AGE_BAND_OVERDUE,
    ArrearsService,
    debt_age_band,
)
from app.models import (
    Class,
    ClassStatus,
    Credit,
    FeeTemplate,
    Payment,
    Student,
    StudentAmountChange,
    StudentStatus,
)

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def arrears(db) -> ArrearsService:
    return ArrearsService(db)


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


def add_payment(session, student_id, amount_cents, month, year) -> Payment:
    payment = Payment(
        student_id=student_id,
        amount_cents=amount_cents,
        method="cash",
        paid_on=date(year, month, 1),
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


# ---------------------------------------------------------------------------
# debt age bands: the pinned 30/60-day thresholds
# ---------------------------------------------------------------------------


def test_debt_age_band_pins_the_30_and_60_day_thresholds():
    assert debt_age_band(0) == AGE_BAND_CURRENT
    assert debt_age_band(30) == AGE_BAND_CURRENT
    assert debt_age_band(31) == AGE_BAND_LATE
    assert debt_age_band(60) == AGE_BAND_LATE
    assert debt_age_band(61) == AGE_BAND_OVERDUE


# ---------------------------------------------------------------------------
# Who owes, and how much
# ---------------------------------------------------------------------------


def test_owed_cents_is_expected_minus_paid_minus_credit(session, arrears):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1))
    payment = add_payment(session, student.id, 6000, 3, 2026)  # $60 on a $50 month
    add_credit(session, student.id, 1000, payment=payment)  # excess rolls forward
    session.commit()

    (line,) = arrears.arrears_report(today=date(2026, 6, 1))

    assert line.student.id == student.id
    assert line.owed_cents == 14000  # 4 × $50 expected − $60 received
    assert line.oldest_period_start == date(2026, 4, 1)  # March is settled; April carries the debt


def test_fully_paid_students_are_excluded(session, arrears):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1))
    for month in range(3, 7):
        add_payment(session, student.id, 5000, month, 2026)
    session.commit()

    assert arrears.arrears_report(today=date(2026, 6, 1)) == []


def test_students_whose_credit_covers_everything_are_excluded(session, arrears):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1))
    payment = add_payment(session, student.id, 15000, 3, 2026)  # $150 on a $50 month
    add_credit(session, student.id, 10000, payment=payment)
    session.commit()

    assert arrears.arrears_report(today=date(2026, 5, 1)) == []  # covers Mar + Apr


def test_students_who_never_owed_are_excluded(session, arrears):
    make_billed_student(session, enrolled_on=date(2026, 8, 1))  # after "today"
    session.commit()

    assert arrears.arrears_report(today=date(2026, 6, 1)) == []


# ---------------------------------------------------------------------------
# Age bands in the report, pinned via ``today``
# ---------------------------------------------------------------------------


def test_arrears_report_age_bands_follow_today(session, arrears):
    make_billed_student(session, enrolled_on=date(2026, 3, 1))
    session.commit()

    at_30 = arrears.arrears_report(today=date(2026, 3, 31))
    assert at_30[0].age_days == 30
    assert at_30[0].age_band == AGE_BAND_CURRENT

    at_31 = arrears.arrears_report(today=date(2026, 4, 1))
    assert at_31[0].age_days == 31
    assert at_31[0].age_band == AGE_BAND_LATE

    at_61 = arrears.arrears_report(today=date(2026, 5, 2))
    assert at_61[0].age_days == 62
    assert at_61[0].age_band == AGE_BAND_OVERDUE


# ---------------------------------------------------------------------------
# Ordering and statuses
# ---------------------------------------------------------------------------


def test_oldest_debt_comes_first(session, arrears):
    make_billed_student(session, enrolled_on=date(2026, 3, 1), first="Ada", last="Lovelace")
    make_billed_student(session, enrolled_on=date(2026, 4, 1), first="Grace", last="Hopper")
    session.commit()

    lines = arrears.arrears_report(today=date(2026, 6, 1))

    assert [line.student.full_name for line in lines] == ["Ada Lovelace", "Grace Hopper"]


def test_archived_students_keep_their_arrears(session, arrears):
    make_billed_student(
        session,
        enrolled_on=date(2026, 3, 1),
        archived_on=date(2026, 4, 30),
        status=StudentStatus.INACTIVE,
    )
    session.commit()

    (line,) = arrears.arrears_report(today=date(2026, 6, 1))

    assert line.owed_cents == 10000  # March + April, both unpaid
    assert line.student_status == StudentStatus.INACTIVE


def test_class_and_student_status_are_exposed(session, arrears):
    make_billed_student(
        session,
        enrolled_on=date(2026, 3, 1),
        class_name="Grade 8",
        class_status=ClassStatus.COMPLETED,
    )
    session.commit()

    (line,) = arrears.arrears_report(today=date(2026, 4, 1))

    assert line.class_status == ClassStatus.COMPLETED
    assert line.student_status == StudentStatus.ACTIVE

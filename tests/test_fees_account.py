"""Fee-account derivation: the owed-month range (FW-14/FW-17).

The seam the account view, payments, and reports all derive from — a student's
owed months run from the enrollment month through the archive month (service-
through-period-end) or the current month while active, skipping school-wide
closed months. The monthly comparison itself is covered by the route-level
student-account tests (ticket 07); this module pins the range derivation.
"""

from __future__ import annotations

from datetime import date

from app.charge_status import ChargeStatus
from app.fees.account import is_in_owed_range, month_range, owed_months, student_account
from app.models import Class, ClosedMonth, Student, StudentStatus
from tests.helpers import add_credit, add_payment, make_billed_student


def make_student(session, enrolled_on, archived_on=None) -> Student:
    cls = Class(name="Grade 1")
    session.add(cls)
    session.flush()
    student = Student(
        class_id=cls.id,
        first_name="Ada",
        last_name="Lovelace",
        status=StudentStatus.ACTIVE,
        enrolled_on=enrolled_on,
        archived_on=archived_on,
    )
    session.add(student)
    session.flush()
    return student


# ---------------------------------------------------------------------------
# month_range
# ---------------------------------------------------------------------------


def test_month_range_covers_a_single_month():
    assert month_range((7, 2026), (7, 2026)) == [(7, 2026)]


def test_month_range_is_inclusive_and_ordered():
    assert month_range((11, 2025), (2, 2026)) == [
        (11, 2025),
        (12, 2025),
        (1, 2026),
        (2, 2026),
    ]


# ---------------------------------------------------------------------------
# owed_months
# ---------------------------------------------------------------------------


def test_active_student_owes_from_enrollment_through_the_current_month(session):
    student = make_student(session, date(2026, 1, 5))
    today = date.today()

    assert owed_months(student, set(), today) == month_range(
        (1, 2026), (today.month, today.year)
    )


def test_archived_student_owes_through_the_archive_month(session):
    student = make_student(session, date(2026, 1, 5), archived_on=date(2026, 4, 30))

    assert owed_months(student, set(), date(2026, 8, 1)) == [
        (1, 2026),
        (2, 2026),
        (3, 2026),
        (4, 2026),
    ]


def test_closed_months_are_skipped_inside_the_owed_range(session):
    student = make_student(session, date(2026, 1, 5), archived_on=date(2026, 6, 30))

    assert owed_months(student, {(2, 2026), (5, 2026)}, date(2026, 6, 1)) == [
        (1, 2026),
        (3, 2026),
        (4, 2026),
        (6, 2026),
    ]


def test_closed_months_accept_closedmonth_rows(session):
    student = make_student(session, date(2026, 1, 5), archived_on=date(2026, 3, 31))
    rows = [ClosedMonth(month=2, year=2026)]
    session.add_all(rows)
    session.commit()

    assert owed_months(student, rows, date(2026, 3, 1)) == [(1, 2026), (3, 2026)]


def test_archived_before_enrollment_owes_nothing(session):
    student = make_student(session, date(2026, 6, 1), archived_on=date(2026, 2, 28))

    assert owed_months(student, set(), date(2026, 6, 1)) == []


# ---------------------------------------------------------------------------
# is_in_owed_range
# ---------------------------------------------------------------------------


def test_is_in_owed_range_respects_enrollment_and_archive(session):
    student = make_student(session, date(2026, 1, 5), archived_on=date(2026, 4, 30))
    today = date(2026, 8, 1)

    assert is_in_owed_range(student, 1, 2026, today) is True
    assert is_in_owed_range(student, 4, 2026, today) is True
    assert is_in_owed_range(student, 5, 2026, today) is False
    assert is_in_owed_range(student, 12, 2025, today) is False


# ---------------------------------------------------------------------------
# student_account: the derived per-month comparison (ticket 07)
# ---------------------------------------------------------------------------


def test_excess_payment_becomes_credit_consumed_oldest_owed_month_first(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 5, 31))
    payment = add_payment(session, student.id, 6000, 3, 2026)  # $60 on a $50 month
    add_credit(session, student.id, 1000, payment=payment)  # excess rolls forward (FW-15)
    session.commit()

    account = student_account(session, student, date(2026, 6, 1), set())

    march, april, may = account.lines
    assert march.credit_consumed_cents == 0  # settled by its own payment
    assert april.credit_consumed_cents == 1000  # oldest shortfall covered first (FW-21)
    assert april.remaining_cents == 4000
    assert may.credit_consumed_cents == 0
    assert account.credits_cents == 1000  # the carried credit total (FW-15)


def test_unused_credit_stays_visible_on_the_account_and_lines(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 4, 30))
    payment = add_payment(session, student.id, 8000, 3, 2026)
    add_credit(session, student.id, 3000, payment=payment)
    session.commit()

    account = student_account(session, student, date(2026, 5, 1), set())

    march, april = account.lines
    assert march.credit_consumed_cents == 0
    assert april.credit_consumed_cents == 3000
    assert april.remaining_cents == 2000
    assert account.credits_cents == 3000


def test_month_status_is_paid_partial_unpaid(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 5, 31))
    add_payment(session, student.id, 5000, 3, 2026)  # settled → paid
    add_payment(session, student.id, 2000, 4, 2026)  # some but not all → partial
    session.commit()

    account = student_account(session, student, date(2026, 6, 1), set())

    assert account.lines[0].status == ChargeStatus.PAID
    assert account.lines[1].status == ChargeStatus.PARTIAL
    assert account.lines[2].status == ChargeStatus.UNPAID


def test_credit_consumed_promotes_a_partial_month_to_paid(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 3, 31))
    payment = add_payment(session, student.id, 3000, 3, 2026)
    add_credit(session, student.id, 2000, payment=payment)
    session.commit()

    account = student_account(session, student, date(2026, 4, 1), set())

    (march,) = account.lines
    assert march.paid_cents == 3000
    assert march.credit_consumed_cents == 2000
    assert march.remaining_cents == 0
    assert march.status == ChargeStatus.PAID


def test_totals_expected_paid_credits_and_balance(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 4, 30))
    payment = add_payment(session, student.id, 6000, 3, 2026)
    add_credit(session, student.id, 1000, payment=payment)
    session.commit()

    account = student_account(session, student, date(2026, 5, 1), set())

    assert account.expected_cents == 10000  # two $50 months
    assert account.paid_cents == 6000
    assert account.received_cents == 6000
    assert account.credits_cents == 1000
    assert account.balance_cents == 4000  # expected − received
    assert account.owed_cents == 4000


def test_balance_can_be_negative_when_holding_credit(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 3, 31))
    payment = add_payment(session, student.id, 6000, 3, 2026)
    add_credit(session, student.id, 1000, payment=payment)
    session.commit()

    account = student_account(session, student, date(2026, 5, 1), set())

    assert account.expected_cents == 5000
    assert account.balance_cents == -1000
    assert account.credits_cents == 1000
    assert account.owed_cents == 0


def test_closed_months_are_excluded_from_the_account_lines(session):
    student = make_billed_student(session, enrolled_on=date(2026, 3, 1), archived_on=date(2026, 5, 31))
    session.add(ClosedMonth(month=4, year=2026))
    session.commit()

    closed = session.query(ClosedMonth).all()
    account = student_account(session, student, date(2026, 6, 1), closed)

    assert [(line.month, line.year) for line in account.lines] == [
        (3, 2026),
        (5, 2026),
    ]

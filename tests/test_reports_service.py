"""Reports service: the derived report surfaces (ticket 08).

Business rules only — the single testing seam. Paid/unpaid per month
(``paid_students``) lists every student with an owed month in the period
(closed months excluded) with expected/paid/credit/remaining/status per line
and the report totals; ``list_periods`` unions owed + payment + expense months;
``student_status_rows`` drives the /students paid column; ``income_vs_expense``
stays date-based. Route concerns live in ``test_reports_routes.py``.
"""

from datetime import date

import pytest

from app.arrears.service import ArrearsService
from app.charge_status import ChargeStatus
from app.models import (
    ClassStatus,
    ClosedMonth,
    Expense,
    ExpenseCategory,
    Student,
    StudentStatus,
)
from app.reports.service import ReportService
from tests.helpers import add_credit, add_payment, make_billed_student


@pytest.fixture()
def reports(db) -> ReportService:
    return ReportService(db, arrears=ArrearsService(db))


def period_of(reference: date, delta: int) -> tuple[int, int]:
    """The (month, year) ``delta`` months before/after ``reference``'s month."""
    total = reference.year * 12 + (reference.month - 1) + delta
    return total % 12 + 1, total // 12


def student_ids(session) -> dict[str, int]:
    return {student.full_name: student.id for student in session.query(Student).all()}


# ---------------------------------------------------------------------------
# paid_students: every owed student, expected/paid/credit/remaining/status
# ---------------------------------------------------------------------------


def test_paid_students_exposes_expected_paid_credit_remaining_status(session, reports):
    today = date.today()
    make_billed_student(session, enrolled_on=date(today.year, today.month, 1))
    add_payment(session, student_ids(session)["Ada Lovelace"], 3000, today.month, today.year)
    session.commit()

    report = reports.paid_students(today.month, today.year)

    (line,) = report.lines
    assert line.expected_cents == 5000
    assert line.paid_cents == 3000
    assert line.credit_cents == 0
    assert line.remaining_cents == 2000
    assert line.status == ChargeStatus.PARTIAL
    assert line.class_status == ClassStatus.ACTIVE
    assert line.student_status == StudentStatus.ACTIVE


def test_paid_students_excludes_a_closed_month(session, reports):
    today = date.today()
    make_billed_student(session, enrolled_on=date(today.year, today.month, 1))
    session.add(ClosedMonth(month=today.month, year=today.year))
    session.commit()

    report = reports.paid_students(today.month, today.year)

    assert report.billed_count == 0
    assert report.lines == []


def test_paid_students_includes_an_archived_student_with_an_owed_month(session, reports):
    today = date.today()
    enroll_month, enroll_year = period_of(today, -4)
    owed_month, owed_year = period_of(today, -2)
    make_billed_student(
        session,
        enrolled_on=date(enroll_year, enroll_month, 1),
        archived_on=date(owed_year, owed_month, 28),
        status=StudentStatus.INACTIVE,
    )
    session.commit()

    report = reports.paid_students(owed_month, owed_year)

    (line,) = report.lines
    assert line.expected_cents == 5000
    assert line.student_status == StudentStatus.INACTIVE


def test_paid_students_counts_paid_partial_and_unpaid(session, reports):
    today = date.today()
    enrolled = date(today.year, today.month, 1)
    make_billed_student(session, enrolled_on=enrolled, first="Fully", last="Paid")
    make_billed_student(session, enrolled_on=enrolled, first="Partially", last="Paid")
    make_billed_student(session, enrolled_on=enrolled, first="Never", last="Paid")
    add_payment(session, student_ids(session)["Fully Paid"], 5000, today.month, today.year)
    add_payment(session, student_ids(session)["Partially Paid"], 2000, today.month, today.year)
    session.commit()

    report = reports.paid_students(today.month, today.year)

    assert report.billed_count == 3
    assert report.paid_count == 1
    assert report.partial_count == 1
    assert report.unpaid_count == 1


def test_paid_students_totals_expected_collected_credited_outstanding(session, reports):
    today = date.today()
    enrolled = date(today.year, today.month, 1)
    make_billed_student(session, enrolled_on=enrolled, first="Fully", last="Paid")
    # Enrolled two months ago: $120 tagged there settles that $50 month and leaves
    # $70 credit, which covers last month's shortfall and part of this month's.
    start_month, start_year = period_of(today, -2)
    make_billed_student(
        session, enrolled_on=date(start_year, start_month, 1), first="Carries", last="Credit"
    )
    ids = student_ids(session)
    add_payment(session, ids["Fully Paid"], 5000, today.month, today.year)
    payment = add_payment(session, ids["Carries Credit"], 12000, start_month, start_year)
    add_credit(session, ids["Carries Credit"], 7000, payment=payment)
    session.commit()

    report = reports.paid_students(today.month, today.year)

    assert report.expected_cents == 10000
    assert report.collected_cents == 5000
    assert report.credited_cents == 2000
    assert report.outstanding_cents == 3000


# ---------------------------------------------------------------------------
# list_periods: owed + payment + expense months, newest first
# ---------------------------------------------------------------------------


def test_list_periods_unions_owed_payment_and_expense_months(session, reports):
    today = date.today()
    owed = (today.month, today.year)
    payment_month, payment_year = period_of(today, -3)
    expense_month, expense_year = period_of(today, -2)

    make_billed_student(session, enrolled_on=date(today.year, today.month, 1))
    student_id = student_ids(session)["Ada Lovelace"]
    add_payment(
        session,
        student_id,
        5000,
        payment_month,
        payment_year,
        paid_on=date(payment_year, payment_month, 5),
    )
    category = ExpenseCategory(name="Utilities")
    session.add(category)
    session.flush()
    session.add(
        Expense(
            category_id=category.id,
            description="Bus fuel",
            amount_cents=2000,
            method="cash",
            occurred_on=date(expense_year, expense_month, 10),
        )
    )
    session.commit()

    periods = reports.list_periods()

    expected = {owed, (payment_month, payment_year), (expense_month, expense_year)}
    assert set(periods) == expected
    assert periods == sorted(expected, reverse=True)


# ---------------------------------------------------------------------------
# student_status_rows: the /students paid column
# ---------------------------------------------------------------------------


def test_student_status_rows_status_for_owed_month_none_otherwise(session, reports):
    today = date.today()
    owed_student = make_billed_student(
        session, enrolled_on=date(today.year, today.month, 1), first="Ada", last="Lovelace"
    )
    last_month, last_year = period_of(today, -1)
    not_owed_student = make_billed_student(
        session,
        enrolled_on=date(last_year, last_month, 1),
        archived_on=date(last_year, last_month, 28),
        first="Grace",
        last="Hopper",
    )
    session.commit()

    rows = reports.student_status_rows(
        [owed_student, not_owed_student], today.month, today.year
    )

    by_name = {row.student.full_name: row for row in rows}
    assert by_name["Ada Lovelace"].paid_status == ChargeStatus.UNPAID
    assert by_name["Ada Lovelace"].remaining_cents == 5000
    assert by_name["Grace Hopper"].paid_status is None
    assert by_name["Grace Hopper"].remaining_cents == 0


def test_student_status_rows_filter_drops_non_matching(session, reports):
    today = date.today()
    owed_student = make_billed_student(
        session, enrolled_on=date(today.year, today.month, 1), first="Ada", last="Lovelace"
    )
    last_month, last_year = period_of(today, -1)
    not_owed_student = make_billed_student(
        session,
        enrolled_on=date(last_year, last_month, 1),
        archived_on=date(last_year, last_month, 28),
        first="Grace",
        last="Hopper",
    )
    session.commit()

    rows = reports.student_status_rows(
        [owed_student, not_owed_student],
        today.month,
        today.year,
        status=ChargeStatus.UNPAID,
    )

    assert [row.student.id for row in rows] == [owed_student.id]


# ---------------------------------------------------------------------------
# income_vs_expense stays date-based
# ---------------------------------------------------------------------------


def test_income_vs_expense_counts_payments_by_paid_on_not_tag(session, reports):
    today = date.today()
    last_month, last_year = period_of(today, -1)
    make_billed_student(session, enrolled_on=date(last_year, last_month, 1))
    student_id = student_ids(session)["Ada Lovelace"]
    # $40 dated inside the month counts; $20 tagged to this month but dated last
    # month does not — income follows ``paid_on``, not the month tag.
    add_payment(
        session, student_id, 4000, today.month, today.year, paid_on=date(today.year, today.month, 5)
    )
    add_payment(
        session, student_id, 2000, today.month, today.year, paid_on=date(last_year, last_month, 10)
    )
    session.commit()

    report = reports.income_vs_expense(today.month, today.year)

    assert report.income_cents == 4000
    assert report.income_by_method[0].amount_cents == 4000

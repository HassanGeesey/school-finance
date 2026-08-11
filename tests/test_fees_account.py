"""Fee-account derivation: the owed-month range (FW-14/FW-17).

The seam the account view, payments, and reports all derive from — a student's
owed months run from the enrollment month through the archive month (service-
through-period-end) or the current month while active, skipping school-wide
closed months. The monthly comparison itself is covered by the route-level
student-account tests (ticket 07); this module pins the range derivation.
"""

from __future__ import annotations

from datetime import date

from app.fees.account import is_in_owed_range, month_range, owed_months
from app.models import Class, ClosedMonth, Student, StudentStatus


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

"""Arrears service layer: the outstanding-money report.

Arrears are **derived** from the expected-vs-paid comparison (ticket 08): for
each student the account assembly (:func:`app.fees.account.student_account`)
computes the expected amount, payments, and carried credit per owed month. A
student is in arrears when their balance — expected minus received — is
positive. Routes are thin adapters over this module — it is the single
testing seam.

Rules that live here:
- Arrears = accumulated monthly shortfalls across owed months. The balance
  ``max(expected - received, 0)`` equals that sum once credit has been
  applied oldest-owed-month-first, so a student who has paid exactly what they
  owe — or holds enough credit — owes nothing and is excluded.
- Debt age is measured from the **oldest owed month still carrying a shortfall**
  (its period start, the first day of that month). ``age_days`` is the days
  since that date (floored at zero) and ``age_band`` classifies it: current
  (<= 30 days), late (31-60 days, amber in the UI), or overdue (> 60 days, red
  in the UI).
- Archived students and students in Completed/Inactive classes keep their
  arrears and still appear — they are never excluded by status.
- Students with no outstanding balance — fully paid, holding enough credit, or
  never owed — are excluded from the report.
- The report is ordered by oldest debt first (then amount owed, largest
  first), so the most urgent debt is on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, joinedload

from ..db import Database
from ..fees.account import student_account
from ..fees.service import period_label
from ..models import ClosedMonth, Student
from ..money import Money
from ..tenants.scope import require_scope, scoped_campus_filter

LATE_THRESHOLD_DAYS = 30
OVERDUE_THRESHOLD_DAYS = 60

AGE_BAND_CURRENT = "current"
AGE_BAND_LATE = "late"
AGE_BAND_OVERDUE = "overdue"

AGE_BAND_LABELS = {
    AGE_BAND_CURRENT: "0-30 days",
    AGE_BAND_LATE: "31-60 days",
    AGE_BAND_OVERDUE: "Over 60 days",
}


def debt_age_band(age_days: int) -> str:
    """Classify a debt's age: current, late (amber), or overdue (red).

    Amber starts above 30 days, red above 60 days, per the UI decisions
    (``UI-12``). Exactly on a threshold keeps the milder band.
    """
    if age_days > OVERDUE_THRESHOLD_DAYS:
        return AGE_BAND_OVERDUE
    if age_days > LATE_THRESHOLD_DAYS:
        return AGE_BAND_LATE
    return AGE_BAND_CURRENT


@dataclass
class ArrearsLine:
    """One owing student's row in the arrears report.

    ``owed_cents`` is what they still owe (expected minus received);
    ``oldest_period_label`` names the month of their oldest unpaid shortfall,
    and ``age_days``/``age_band`` describe how old that debt is.
    """

    student: Student
    class_name: str
    class_status: str
    student_status: str
    owed_cents: Money
    oldest_period_label: str
    oldest_period_start: date
    age_days: int
    age_band: str


class ArrearsService:
    """Arrears business rules. Read-only; each method is one unit of work."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _session(self) -> Session:
        return self._db.session()

    @staticmethod
    def _closed_months(session: Session) -> set[tuple[int, int]]:
        query = session.query(ClosedMonth.month, ClosedMonth.year)
        cur = require_scope()
        if cur is not None:
            query = query.filter(
                scoped_campus_filter(session, cur, ClosedMonth.campus_id)
            )
        rows = query.all()
        return {(month, year) for month, year in rows}

    def arrears_report(self, *, today: date | None = None) -> list[ArrearsLine]:
        """Every student with outstanding arrears, oldest debt first.

        A single pass over all students builds each one's derived account; a
        student whose balance (expected - paid - credit) is not positive is
        dropped. ``today`` is injectable so tests can pin the debt ages; it
        defaults to the real date.
        """
        today = today or date.today()
        lines: list[ArrearsLine] = []
        with self._session() as session:
            query = (
                session.query(Student)
                .options(joinedload(Student.school_class))
            )
            cur = require_scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Student.campus_id))
            students = (
                query.order_by(Student.last_name, Student.first_name, Student.id)
                .all()
            )
            closed = self._closed_months(session)

            for student in students:
                account = student_account(session, student, today, closed)
                owed = account.owed_cents
                if owed <= 0:
                    continue
                oldest = min(
                    (line.year, line.month)
                    for line in account.lines
                    if line.remaining_cents > 0
                )
                oldest_start = date(oldest[0], oldest[1], 1)
                age_days = max((today - oldest_start).days, 0)
                lines.append(
                    ArrearsLine(
                        student=student,
                        class_name=student.school_class.name,
                        class_status=student.school_class.status,
                        student_status=student.status,
                        owed_cents=owed,
                        oldest_period_label=period_label(oldest[1], oldest[0]),
                        oldest_period_start=oldest_start,
                        age_days=age_days,
                        age_band=debt_age_band(age_days),
                    )
                )
        lines.sort(key=lambda line: (line.oldest_period_start, -line.owed_cents))
        return lines

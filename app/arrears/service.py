"""Arrears service layer: the outstanding-money report.

Business rules for the report the office uses to chase unpaid fees. A student
is in arrears when their unpaid charge balances exceed their credits; the
report lists every such student with how much they owe and how old the debt is.
Routes are thin adapters over this module — it is the single testing seam.

Rules that live here:
- Arrears = unpaid charge balances minus credits. A charge's unpaid balance is
  its live net amount (base + extras - waivers) minus what payments have
  cleared, floored at zero. ``owed_cents`` is ``max(outstanding - credits, 0)``
  so a student who has paid exactly what they owe — or holds a credit — owes
  nothing and is excluded.
- Debt age is measured from the oldest *unpaid* charge's period start (the
  first day of the month the charge covers). This is stable regardless of when
  fees were generated and matches how the office thinks of a month's fees
  going unpaid. ``age_days`` is the days since that date (floored at zero for
  charges that have not become due yet) and ``age_band`` classifies it:
  current (<= 30 days), late (31-60 days, amber in the UI), or overdue (> 60
  days, red in the UI).
- Archived students (``StudentStatus.INACTIVE``) and students in
  Completed/Inactive classes keep their arrears and still appear — they are
  never excluded by status.
- Students with no outstanding balance — fully paid, holding enough credit, or
  never billed — are excluded from the report.
- The report is ordered by oldest debt first (then amount owed, largest
  first), so the most urgent debt is on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..db import Database
from ..fees.service import net_cents, period_label
from ..models import Charge, Credit, Student
from ..money import Money
from ..payments.planner import paid_cents_by_charge

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

    ``owed_cents`` is what they still owe (unpaid charge balances minus
    credits); ``oldest_period_label`` names the month of their oldest unpaid
    charge, and ``age_days``/``age_band`` describe how old that debt is.
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
    def _credits_by_student(session: Session) -> dict[int, int]:
        """Total credit held per student."""
        rows = (
            session.query(Credit.student_id, func.sum(Credit.amount_cents))
            .group_by(Credit.student_id)
            .all()
        )
        return {student_id: int(total) for student_id, total in rows}

    def arrears_report(self, *, today: date | None = None) -> list[ArrearsLine]:
        """Every student with outstanding arrears, oldest debt first.

        A single pass over all charges builds each student's outstanding amount
        (net of adjustments and payments) and their oldest unpaid charge
        period; credits are then subtracted and any student whose resulting
        arrears are not positive is dropped. ``today`` is injectable so tests
        can pin the debt ages; it defaults to the real date.
        """
        today = today or date.today()
        with self._session() as session:
            charges = (
                session.query(Charge)
                .options(
                    joinedload(Charge.adjustments),
                    joinedload(Charge.student).joinedload(Student.school_class),
                )
                .all()
            )
            paid_by_charge = paid_cents_by_charge(session)
            credits_by_student = self._credits_by_student(session)

        by_student: dict[int, tuple[Student, int, tuple[int, int]]] = {}
        for charge in charges:
            unpaid = max(
                net_cents(charge, list(charge.adjustments))
                - paid_by_charge.get(charge.id, 0),
                0,
            )
            if unpaid <= 0:
                continue
            student = charge.student
            student_entry, outstanding, oldest = by_student.get(
                student.id, (student, 0, (9999, 13))
            )
            period = (charge.year, charge.month)
            by_student[student.id] = (
                student_entry,
                outstanding + unpaid,
                min(oldest, period),
            )

        lines: list[ArrearsLine] = []
        for student, outstanding, (year, month) in by_student.values():
            owed = max(outstanding - credits_by_student.get(student.id, 0), 0)
            if owed <= 0:
                continue
            oldest_start = date(year, month, 1)
            age_days = max((today - oldest_start).days, 0)
            lines.append(
                ArrearsLine(
                    student=student,
                    class_name=student.school_class.name,
                    class_status=student.school_class.status,
                    student_status=student.status,
                    owed_cents=owed,
                    oldest_period_label=period_label(month, year),
                    oldest_period_start=oldest_start,
                    age_days=age_days,
                    age_band=debt_age_band(age_days),
                )
            )
        lines.sort(key=lambda line: (line.oldest_period_start, -line.owed_cents))
        return lines

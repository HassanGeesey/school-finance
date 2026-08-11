"""Derived fee-billing engine: the expected-vs-paid comparison.

The fee-billing rework replaced charge rows with a derivation (``CONTEXT.md`` —
"Fee billing"). A student's account is *computed* from their enrollment, their
effective-dated monthly amount, waivers, month-tagged payments, and credit —
there is no generation step and no charge table. This module is the single seam
the account view, payments, arrears, and reports all derive from.

Derivation rules (pinned in ``project-decisions.md`` — FW-10..FW-22):

- **Owed months** run from the month of ``enrolled_on`` through the month of
  ``archived_on`` (service-through-period-end) — or the current month for an
  active student with no archive date — excluding school-wide ``ClosedMonth``
  rows (FW-14, FW-17).
- **Amount in force** for a month is the latest ``StudentAmountChange`` on or
  before it; before the first change the linked template's current amount
  applies. Past months are never rewritten by a later change (FW-20).
- **Expected** = amount in force - stacked waivers for the month, never below
  zero (FW-10/FW-11).
- **Paid** per month = the sum of payments tagged to that month. Excess over a
  month's expected becomes credit (FW-15); credit covers the oldest owed
  months' shortfalls first, visibly per month (FW-21).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..charge_status import ChargeStatus, classify_paid_status
from ..models import ClosedMonth, Credit, Payment, Student, StudentAmountChange, Waiver
from ..money import Money
from .service import period_label


def month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Every (month, year) pair from ``start`` through ``end`` inclusive."""
    months: list[tuple[int, int]] = []
    month, year = start
    end_month, end_year = end
    while (year, month) <= (end_year, end_month):
        months.append((month, year))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def owed_months(
    student: Student,
    closed_months: Iterable[ClosedMonth] | set[tuple[int, int]],
    today: date,
) -> list[tuple[int, int]]:
    """The (month, year) pairs a student is expected to pay for, oldest first.

    Starts in the month of ``enrolled_on`` and ends in the month of
    ``archived_on`` — or the current month for an active student — skipping
    every closed month (FW-14/FW-17). ``closed_months`` is either an iterable
    of :class:`ClosedMonth` rows or an already-materialised set of
    ``(month, year)`` pairs.
    """
    if isinstance(closed_months, set):
        closed = closed_months
    else:
        closed = {(row.month, row.year) for row in closed_months}
    start = (student.enrolled_on.month, student.enrolled_on.year)
    if student.archived_on is not None:
        end = (student.archived_on.month, student.archived_on.year)
    else:
        end = (today.month, today.year)
    if (start[1], start[0]) > (end[1], end[0]):
        return []
    return [period for period in month_range(start, end) if period not in closed]


def is_in_owed_range(student: Student, month: int, year: int, today: date) -> bool:
    """Whether ``(month, year)`` falls inside the student's owed range
    (enrolled month through archived/current month), ignoring closed months.

    Used when a payment tags a month that is not one of the currently owed
    months — e.g. a future month within the range, or one before enrollment —
    to decide whether the tag carries an expected amount at all.
    """
    start = (student.enrolled_on.year, student.enrolled_on.month)
    if student.archived_on is not None:
        end = (student.archived_on.year, student.archived_on.month)
    else:
        end = (today.year, today.month)
    return start <= (year, month) <= end


def amount_in_force(session: Session, student: Student, month: int, year: int) -> Money:
    """The monthly amount in force for ``(month, year)`` (FW-20).

    The latest :class:`StudentAmountChange` on or before the month wins; before
    the first effective-dated change the linked template's current amount
    applies. Students whose amount was never seeded resolve to 0.
    """
    change = (
        session.query(StudentAmountChange)
        .filter(
            StudentAmountChange.student_id == student.id,
            or_(
                StudentAmountChange.year < year,
                and_(
                    StudentAmountChange.year == year,
                    StudentAmountChange.month <= month,
                ),
            ),
        )
        .order_by(
            StudentAmountChange.year.desc(),
            StudentAmountChange.month.desc(),
            StudentAmountChange.id.desc(),
        )
        .first()
    )
    if change is not None:
        return int(change.amount_cents)
    if student.fee_template is not None:
        return int(student.fee_template.amount_cents)
    return 0


def expected_cents(
    session: Session,
    student: Student,
    month: int,
    year: int,
    closed_months: Iterable[ClosedMonth] | set[tuple[int, int]],
    today: date,
    waivers_cents: int | None = None,
) -> int:
    """What a student is expected to pay for one month.

    Zero for a closed month or a month outside the owed range (nothing is owed,
    so a payment tagged there becomes credit); otherwise amount in force minus
    stacked waivers, never below zero. ``waivers_cents`` may be passed in to
    avoid a redundant query when the caller already has it.
    """
    closed = closed_months if isinstance(closed_months, set) else {
        (row.month, row.year) for row in closed_months
    }
    if (month, year) in closed or not is_in_owed_range(student, month, year, today):
        return 0
    if waivers_cents is None:
        waivers_cents = waivers_for_month(session, student.id, month, year)
    return max(amount_in_force(session, student, month, year) - waivers_cents, 0)


def waivers_for_month(session: Session, student_id: int, month: int, year: int) -> int:
    """Total waiver cents stacked on one (student, month)."""
    rows = (
        session.query(Waiver)
        .filter(
            Waiver.student_id == student_id,
            Waiver.month == month,
            Waiver.year == year,
        )
        .all()
    )
    return sum(row.amount_cents for row in rows)


@dataclass
class MonthLine:
    """One owed month in a student's account comparison."""

    month: int
    year: int
    period_label: str
    amount_in_force_cents: Money
    waivers_cents: Money
    expected_cents: Money
    paid_cents: Money
    credit_consumed_cents: Money
    remaining_cents: Money
    status: str
    waivers: list[Waiver] = field(default_factory=list)

    @property
    def settled_cents(self) -> int:
        """Payments plus carried credit applied to this month."""
        return self.paid_cents + self.credit_consumed_cents


@dataclass
class AccountView:
    """A student's full account comparison and its running totals.

    ``balance_cents`` is ``expected - received`` — the net position, positive
    when the student still owes and negative when they hold credit (FW-15).
    ``received_cents`` is every payment ever recorded (including what became
    credit); ``paid_cents`` is the sum of payments tagged to the owed months
    shown; ``credits_cents`` is the total credit carried on the account (the
    per-month Credit column shows how much each month consumed).
    """

    student: Student
    lines: list[MonthLine]
    expected_cents: Money
    paid_cents: Money
    received_cents: Money
    credits_cents: Money
    balance_cents: Money
    payments: list[Payment] = field(default_factory=list)
    credits: list[Credit] = field(default_factory=list)

    @property
    def owed_cents(self) -> int:
        """What is actually still owed: the positive side of the balance."""
        return max(self.balance_cents, 0)


def student_account(
    session: Session,
    student: Student,
    today: date,
    closed_months: Iterable[ClosedMonth] | set[tuple[int, int]],
) -> AccountView:
    """Assemble the derived account for one student.

    The credit pass (FW-21) walks the owed months oldest first and consumes the
    student's total credit against each month's shortfall until exhausted. A
    month's status is paid/partial/unpaid from expected vs paid + credit
    consumed.
    """
    months = owed_months(student, closed_months, today)
    waivers_by_month: dict[tuple[int, int], list[Waiver]] = {}
    for waiver in session.query(Waiver).filter(Waiver.student_id == student.id).all():
        waivers_by_month.setdefault((waiver.month, waiver.year), []).append(waiver)
    payments_by_month: dict[tuple[int, int], int] = {}
    payments = (
        session.query(Payment)
        .filter(Payment.student_id == student.id)
        .order_by(Payment.paid_on.desc(), Payment.id.desc())
        .all()
    )
    for payment in payments:
        payments_by_month[(payment.month, payment.year)] = (
            payments_by_month.get((payment.month, payment.year), 0)
            + payment.amount_cents
        )
    credits = session.query(Credit).filter(Credit.student_id == student.id).all()
    credits_cents = sum(credit.amount_cents for credit in credits)

    lines: list[MonthLine] = []
    for month, year in months:
        month_waivers = waivers_by_month.get((month, year), [])
        waivers_cents = sum(waiver.amount_cents for waiver in month_waivers)
        amount = amount_in_force(session, student, month, year)
        expected = max(amount - waivers_cents, 0)
        lines.append(
            MonthLine(
                month=month,
                year=year,
                period_label=period_label(month, year),
                amount_in_force_cents=amount,
                waivers_cents=waivers_cents,
                expected_cents=expected,
                paid_cents=payments_by_month.get((month, year), 0),
                credit_consumed_cents=0,
                remaining_cents=0,
                status=ChargeStatus.UNPAID,
                waivers=month_waivers,
            )
        )

    pool = credits_cents
    for line in lines:
        if pool <= 0:
            break
        shortfall = max(line.expected_cents - line.paid_cents, 0)
        if shortfall <= 0:
            continue
        consumed = min(pool, shortfall)
        line.credit_consumed_cents = consumed
        pool -= consumed

    expected_cents = 0
    paid_cents = 0
    for line in lines:
        expected_cents += line.expected_cents
        paid_cents += line.paid_cents
        settled = line.settled_cents
        line.remaining_cents = max(line.expected_cents - settled, 0)
        line.status, _ = classify_paid_status(line.expected_cents, settled)

    received_cents = sum(payment.amount_cents for payment in payments)
    # The net position: every dollar received either settles expected or is
    # held as credit, so ``expected - received`` is never double counted
    # (paid_cents already includes the part that became credit).
    balance_cents = expected_cents - received_cents
    return AccountView(
        student=student,
        lines=lines,
        expected_cents=expected_cents,
        paid_cents=paid_cents,
        received_cents=received_cents,
        credits_cents=credits_cents,
        balance_cents=balance_cents,
        payments=payments,
        credits=credits,
    )


def month_comparison(
    session: Session,
    student: Student,
    month: int,
    year: int,
    today: date,
    closed_months: Iterable[ClosedMonth] | set[tuple[int, int]],
) -> MonthLine | None:
    """One owed month's comparison, using the full credit pass.

    Returns ``None`` when the student is not owed that month (never billed —
    closed, outside the range, or before/after enrollment) — callers treat that
    as "does not owe". Credit consumed reflects the whole account pass, so a
    carried credit visibly covers this month's shortfall when it is the oldest
    one (FW-21).
    """
    if (month, year) not in owed_months(student, closed_months, today):
        return None
    account = student_account(session, student, today, closed_months)
    for line in account.lines:
        if line.month == month and line.year == year:
            return line
    return None


def oldest_unpaid_period(
    session: Session,
    student: Student,
    today: date,
    closed_months: Iterable[ClosedMonth] | set[tuple[int, int]],
) -> tuple[int, int] | None:
    """The oldest owed month still carrying a shortfall, for the record-payment
    screen's default month tag (FW-22-1). ``None`` when nothing is unpaid.
    """
    account = student_account(session, student, today, closed_months)
    for line in account.lines:
        if line.remaining_cents > 0:
            return line.year, line.month
    return None

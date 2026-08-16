"""Payments & receipts service layer.

Business rules for recording money in: a payment carries a **month+year tag**
(FW-16) and is recorded as ``(student, tagged month, amount, method, date)``.
The tag is the clerk's entry — the record screen surfaces the student's oldest
unpaid owed month first (FW-22-1) and warns, rather than blocks, when the tag
falls outside the owed range (FW-22-2, e.g. a fat-fingered future month or a
closed month). A payment first covers the tagged month's shortfall (its
expected amount minus payments already tagged to it); any excess rolls forward
as :class:`Credit` on the account (FW-15/FW-21), consumed by the oldest owed
months' shortfalls in the derived account view
(:func:`app.fees.account.student_account`).

Routes are thin adapters over this module — it is the single testing seam.

Rules that live here:
- Amounts are positive integer cents (``app.money``), never floats.
- The method is one of cash/bank/other (``PaymentMethods``).
- The payment date must parse and cannot be in the future.
- The tagged month must be a valid month/year pair; any value is recordable
  (warning is a UI concern, not a service rejection).
- ``applied`` is the amount that settles the tagged month's shortfall;
  ``credit`` is the excess — it becomes a ``Credit`` row linked to the payment.
- Every recorded payment writes one audit entry; a rejected payment writes
  nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..fees.account import AccountView, expected_cents, owed_months, student_account
from ..fees.service import MIN_YEAR, MAX_YEAR, period_label
from ..models import ClosedMonth, Credit, Payment, PaymentMethods, Student, User
from ..money import (
    InvalidAmount,
    Money,
    NonPositiveAmount,
    format_cents,
    parse_positive_cents,
)
from ..students.service import StudentNotFound
from ..tenants.scope import (
    campus_for_write,
    in_scope,
    scope,
    scoped_campus_filter,
)

PAYMENT_METHOD_LABELS = {
    PaymentMethods.CASH: "Cash",
    PaymentMethods.BANK: "Bank",
    PaymentMethods.OTHER: "Other",
}
VALID_PAYMENT_METHODS = set(PAYMENT_METHOD_LABELS)


class PaymentError(Exception):
    """Rejected input or state in a payment operation."""


class InvalidMethod(PaymentError):
    """The payment method is not one of cash/bank/other."""


class InvalidDate(PaymentError):
    """The payment date is unparsable or lies in the future."""


class InvalidPeriod(PaymentError):
    """The tagged month/year falls outside the supported range."""


class PaymentNotFound(PaymentError):
    """No payment exists with the given id."""


@dataclass
class PaymentPreview:
    """Where a payment tagged to one month would go, without writing anything.

    ``applied_cents`` is what would settle the tagged month's remaining
    shortfall and ``credit_cents`` what would roll forward as credit.
    ``in_owed_range`` is ``False`` when the tag lies outside the student's owed
    range (a closed month, a future month, or one before enrollment) — the
    record screen warns but does not block (FW-22-2).
    """

    month: int
    year: int
    period_label: str
    expected_cents: Money
    paid_cents: Money
    remaining_cents: Money
    applied_cents: Money
    credit_cents: Money
    in_owed_range: bool


@dataclass
class AccountSummary:
    """A student's live account plus the record screen's default month tag."""

    account: AccountView
    oldest_unpaid: tuple[int, int] | None


class PaymentService:
    """Payment business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    @staticmethod
    def _closed_months(session: Session) -> set[tuple[int, int]]:
        query = session.query(ClosedMonth.month, ClosedMonth.year)
        cur = scope()
        if cur is not None:
            query = query.filter(
                scoped_campus_filter(session, cur, ClosedMonth.campus_id)
            )
        rows = query.all()
        return {(month, year) for month, year in rows}

    @staticmethod
    def _validate_amount(amount: object) -> int:
        try:
            return parse_positive_cents(amount)  # type: ignore[arg-type]
        except InvalidAmount:
            raise PaymentError("Enter a valid amount.") from None
        except NonPositiveAmount:
            raise PaymentError("Amount must be greater than zero.") from None

    @staticmethod
    def _validate_method(method: str) -> str:
        if method not in VALID_PAYMENT_METHODS:
            raise InvalidMethod("Choose Cash, Bank, or Other.")
        return method

    @staticmethod
    def _validate_date(value: object) -> date:
        if isinstance(value, date):
            paid_on = value
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                raise InvalidDate("Choose a payment date.")
            try:
                paid_on = date.fromisoformat(raw)
            except ValueError:
                raise InvalidDate("Enter a valid payment date.") from None
        else:
            raise InvalidDate("Choose a payment date.")
        if paid_on > date.today():
            raise InvalidDate("Payment date cannot be in the future.")
        return paid_on

    @staticmethod
    def _validate_period(month: int | None, year: int | None) -> tuple[int, int]:
        if not isinstance(month, int) or not 1 <= month <= 12:
            raise InvalidPeriod("Choose a month between 1 and 12.")
        if not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
            raise InvalidPeriod(f"Choose a year between {MIN_YEAR} and {MAX_YEAR}.")
        return month, year

    @staticmethod
    def _get_student(session: Session, student_id: int) -> Student:
        student = (
            session.query(Student)
            .options(joinedload(Student.school_class))
            .filter(Student.id == student_id)
            .one_or_none()
        )
        if student is None:
            raise StudentNotFound(f"No student with id {student_id} exists.")
        cur = scope()
        if cur is not None and not in_scope(session, cur, student.campus_id):
            raise StudentNotFound(f"No student with id {student_id} exists.")
        return student

    def account_summary(self, student_id: int) -> AccountSummary:
        """A student's live account and the oldest still-unpaid owed month.

        The latter is the record screen's default month tag (FW-22-1): ``None``
        when nothing is unpaid.
        """
        with self._session() as session:
            student = self._get_student(session, student_id)
            closed = self._closed_months(session)
            today = date.today()
            account = student_account(session, student, today, closed)
            oldest_unpaid = next(
                (
                    (line.year, line.month)
                    for line in account.lines
                    if line.remaining_cents > 0
                ),
                None,
            )
        return AccountSummary(account=account, oldest_unpaid=oldest_unpaid)

    def preview_application(
        self, student_id: int, month: int, year: int, amount: object
    ) -> PaymentPreview:
        """Show where a payment tagged to one month would go, nothing written."""
        amount_cents = self._validate_amount(amount)
        with self._session() as session:
            student = self._get_student(session, student_id)
            closed = self._closed_months(session)
            today = date.today()
            expected = expected_cents(session, student, month, year, closed, today)
            paid = self._month_paid(session, student_id, month, year)
            remaining = max(expected - paid, 0)
            applied = min(amount_cents, remaining)
            credit = amount_cents - applied
        return PaymentPreview(
            month=month,
            year=year,
            period_label=period_label(month, year),
            expected_cents=expected,
            paid_cents=paid,
            remaining_cents=remaining,
            applied_cents=applied,
            credit_cents=credit,
            in_owed_range=(month, year) in owed_months(student, closed, today),
        )

    @staticmethod
    def _month_paid(session: Session, student_id: int, month: int, year: int) -> int:
        """Total cents already tagged to one (student, month)."""
        query = session.query(Payment.amount_cents).filter(
            Payment.student_id == student_id,
            Payment.month == month,
            Payment.year == year,
        )
        cur = scope()
        if cur is not None:
            query = query.filter(scoped_campus_filter(session, cur, Payment.campus_id))
        rows = query.all()
        return sum(amount for (amount,) in rows)

    def record_payment(
        self,
        *,
        user: User | None,
        student_id: int,
        amount: object,
        method: str,
        paid_on: object,
        month: int | None,
        year: int | None,
    ) -> Payment:
        """Record one month-tagged payment, excess to credit, in one transaction.

        The payment is tagged to ``(month, year)``. It settles the tagged
        month's shortfall (expected minus what is already tagged there); the
        excess becomes a ``Credit`` on the account. The payment, any credit,
        and the audit entry land atomically — a rejected payment writes nothing.
        """
        amount_cents = self._validate_amount(amount)
        method = self._validate_method(method)
        paid_on = self._validate_date(paid_on)
        month, year = self._validate_period(month, year)

        with self._session() as session:
            student = self._get_student(session, student_id)
            closed = self._closed_months(session)
            today = date.today()
            expected = expected_cents(session, student, month, year, closed, today)
            already_paid = self._month_paid(session, student_id, month, year)
            applied = min(amount_cents, max(expected - already_paid, 0))
            credit = amount_cents - applied

            payment = Payment(
                student_id=student_id,
                amount_cents=amount_cents,
                method=method,
                paid_on=paid_on,
                month=month,
                year=year,
                campus_id=campus_for_write(scope()),
                recorded_by=user.id if user is not None else None,
            )
            session.add(payment)
            session.flush()
            if credit > 0:
                session.add(
                    Credit(
                        student_id=student_id,
                        amount_cents=credit,
                        payment_id=payment.id,
                        campus_id=campus_for_write(scope()),
                    )
                )

            summary = (
                f"Recorded payment of {format_cents(amount_cents)} from "
                f"{student.full_name} via {PAYMENT_METHOD_LABELS[method]} on "
                f"{paid_on.isoformat()} for {period_label(month, year)}"
            )
            if applied:
                summary += f" ({format_cents(applied)} applied)"
            if credit > 0:
                summary += f" — excess {format_cents(credit)} placed on account as credit"
            if self._audit is not None:
                self._audit.add(
                    session,
                    user=user,
                    action=AuditActions.PAYMENT_RECORD,
                    summary=summary,
                )
            session.commit()
            session.refresh(payment)
        return payment

    def get_payment(self, payment_id: int) -> Payment:
        """One payment with its student and class (for receipts)."""
        with self._session() as session:
            query = (
                session.query(Payment)
                .options(joinedload(Payment.student).joinedload(Student.school_class))
                .filter(Payment.id == payment_id)
            )
            cur = scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Payment.campus_id))
            payment = query.one_or_none()
        if payment is None:
            raise PaymentNotFound(f"No payment with id {payment_id} exists.")
        return payment

    def list_recent_payments(self, limit: int = 10) -> list[Payment]:
        """The most recent payments visible to the acting Campus, for the payments page."""
        with self._session() as session:
            query = session.query(Payment).options(
                joinedload(Payment.student).joinedload(Student.school_class)
            )
            cur = scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Payment.campus_id))
            return (
                query.order_by(Payment.created_at.desc(), Payment.id.desc())
                .limit(limit)
                .all()
            )

"""Payments & receipts service layer.

Business rules for recording money in: a payment (amount + method + date) is
recorded against a student and, in one transaction, applied to the oldest unpaid
charges first — partial application is supported. If the payment exceeds what is
owed, the excess becomes a :class:`Credit` on the student's account (no refunds
in v1). The student's account view — charges with their paid/remaining status,
payments, credits, and the live balance — is assembled here, and every payment
is recorded in the audit log.

Routes are thin adapters over this module — it is the single testing seam.

Rules that live here:
- Amounts are positive integer cents (``app.money``), never floats.
- The method is one of cash/bank/other (``PaymentMethods``).
- The payment date must parse and cannot be in the future.
- A payment clears the oldest unpaid charges first (per student): charges are
  taken in year/month/id order and each is reduced until it is settled before
  the next is touched. Already-settled charges are skipped.
- A charge's remaining amount is net of its adjustments (base + extras -
  waivers) and of earlier allocations; waivers never push a charge below zero,
  so a remaining amount is never negative.
- Overpayment becomes a ``Credit`` row linked to the payment; the live balance
  is outstanding minus credits and may therefore be negative (a credit balance).
- Every recorded payment writes one audit entry; a rejected payment writes
  nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..charge_status import classify_paid_status
from ..db import Database
from ..fees.service import (
    ChargeAccountLine,
    period_label,
    to_charge_line,
)
from ..models import (
    Charge,
    Credit,
    Payment,
    PaymentAllocation,
    PaymentMethods,
    Student,
    User,
)
from ..money import (
    InvalidAmount,
    Money,
    NonPositiveAmount,
    format_cents,
    parse_positive_cents,
)
from ..students.service import StudentNotFound
from .planner import paid_cents_by_charge, plan_application

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


class PaymentNotFound(PaymentError):
    """No payment exists with the given id."""


@dataclass
class AccountCharge:
    """One monthly charge as shown on a student's account, with its payment state.

    ``remaining_cents`` is the live unpaid amount (net of adjustments and of
    earlier allocations, floored at zero); ``status`` is paid/partial/unpaid.
    The wrapped ``line`` mirrors the account view built by the adjustments
    feature (base + extras - waivers, period label, adjustment rows).
    """

    line: ChargeAccountLine
    paid_cents: Money
    remaining_cents: Money
    status: str

    @property
    def charge(self) -> Charge:
        return self.line.charge

    @property
    def period_label(self) -> str:
        return self.line.period_label

    @property
    def base_cents(self) -> Money:
        return self.line.base_cents

    @property
    def extras_cents(self) -> Money:
        return self.line.extras_cents

    @property
    def waivers_cents(self) -> Money:
        return self.line.waivers_cents

    @property
    def net_cents(self) -> Money:
        return self.line.net_cents

    @property
    def adjusted(self) -> bool:
        return self.line.adjusted

    @property
    def adjustments(self) -> list:
        return self.line.adjustments


@dataclass
class StudentAccount:
    """Everything a student's account page shows."""

    student: Student
    charges: list[AccountCharge]
    payments: list[Payment]
    credits: list[Credit]
    outstanding_cents: Money
    credits_cents: Money
    balance_cents: Money
    received_cents: Money


@dataclass
class PreviewLine:
    """One charge a payment of a given amount would clear, as a preview."""

    period_label: str
    applied_cents: Money


@dataclass
class ApplicationPreview:
    """Where a prospective payment would go, without writing anything.

    ``lines`` lists each charge the payment would reduce (oldest first) and how
    much it would clear; ``applied_cents`` is the total applied to charges and
    ``credit_cents`` is what would become a credit on the account.
    """

    lines: list[PreviewLine]
    applied_cents: Money
    credit_cents: Money


class PaymentService:
    """Payment business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

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
    def _get_student(session: Session, student_id: int) -> Student:
        student = (
            session.query(Student)
            .options(joinedload(Student.school_class))
            .filter(Student.id == student_id)
            .one_or_none()
        )
        if student is None:
            raise StudentNotFound(f"No student with id {student_id} exists.")
        return student

    def record_payment(
        self,
        *,
        user: User | None,
        student_id: int,
        amount: object,
        method: str,
        paid_on: object,
    ) -> Payment:
        """Record one payment, applied oldest-unpaid-first, in one transaction.

        Every unpaid charge is reduced in turn (year/month/id order) until the
        payment is spent; whatever remains becomes a ``Credit`` on the account.
        The payment, its allocations, any credit, and the audit entry land
        atomically — a rejected payment writes nothing.
        """
        amount_cents = self._validate_amount(amount)
        method = self._validate_method(method)
        paid_on = self._validate_date(paid_on)

        with self._session() as session:
            student = self._get_student(session, student_id)
            payment = Payment(
                student_id=student_id,
                amount_cents=amount_cents,
                method=method,
                paid_on=paid_on,
                recorded_by=user.id if user is not None else None,
            )
            session.add(payment)
            session.flush()

            charges = (
                session.query(Charge)
                .options(joinedload(Charge.adjustments))
                .filter(Charge.student_id == student_id)
                .order_by(Charge.year, Charge.month, Charge.id)
                .all()
            )
            paid_by_charge = paid_cents_by_charge(session, [c.id for c in charges])
            applied_by_charge, credit = plan_application(
                charges, paid_by_charge, amount_cents
            )
            for charge_id, applied in applied_by_charge.items():
                session.add(
                    PaymentAllocation(
                        payment_id=payment.id,
                        charge_id=charge_id,
                        amount_cents=applied,
                    )
                )

            if credit > 0:
                session.add(
                    Credit(
                        student_id=student_id,
                        amount_cents=credit,
                        payment_id=payment.id,
                    )
                )

            summary = (
                f"Recorded payment of {format_cents(amount_cents)} from "
                f"{student.full_name} via {PAYMENT_METHOD_LABELS[method]} "
                f"on {paid_on.isoformat()}"
            )
            if credit > 0:
                summary += f" (credit of {format_cents(credit)})"
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

    def preview_application(self, student_id: int, amount: object) -> ApplicationPreview:
        """Show where a payment of ``amount`` would go, without writing anything.

        Mirrors :meth:`record_payment`'s oldest-unpaid-first allocation so the
        record screen can confirm what will be cleared (and what would become a
        credit) before the user saves.
        """
        amount_cents = self._validate_amount(amount)
        with self._session() as session:
            self._get_student(session, student_id)
            charges = (
                session.query(Charge)
                .options(joinedload(Charge.adjustments))
                .filter(Charge.student_id == student_id)
                .order_by(Charge.year, Charge.month, Charge.id)
                .all()
            )
            paid_by_charge = paid_cents_by_charge(session, [c.id for c in charges])
            applied_by_charge, credit = plan_application(
                charges, paid_by_charge, amount_cents
            )
            lines = [
                PreviewLine(
                    period_label=period_label(charge.month, charge.year),
                    applied_cents=applied_by_charge[charge.id],
                )
                for charge in charges
                if charge.id in applied_by_charge
            ]
        return ApplicationPreview(
            lines=lines,
            applied_cents=sum(applied_by_charge.values()),
            credit_cents=credit,
        )

    def get_payment(self, payment_id: int) -> Payment:
        """One payment with its student, class, and charge allocations (for receipts)."""
        with self._session() as session:
            payment = (
                session.query(Payment)
                .options(
                    joinedload(Payment.student).joinedload(Student.school_class),
                    joinedload(Payment.allocations).joinedload(PaymentAllocation.charge),
                )
                .filter(Payment.id == payment_id)
                .one_or_none()
            )
        if payment is None:
            raise PaymentNotFound(f"No payment with id {payment_id} exists.")
        return payment

    def student_account(self, student_id: int) -> StudentAccount:
        """A student's full account: charges, payments, credits, and live balance.

        Charges are listed most recent period first, each with its paid and
        remaining amounts and a paid/partial/unpaid status. ``balance_cents`` is
        the amount still owed — outstanding charges minus credits — and may be
        negative when the student holds a credit.
        """
        with self._session() as session:
            student = self._get_student(session, student_id)
            charges = (
                session.query(Charge)
                .options(joinedload(Charge.adjustments))
                .filter(Charge.student_id == student_id)
                .order_by(Charge.year.desc(), Charge.month.desc(), Charge.id.desc())
                .all()
            )
            paid_by_charge = paid_cents_by_charge(session, [c.id for c in charges])
            account_charges: list[AccountCharge] = []
            for charge in charges:
                line = to_charge_line(charge)
                paid = paid_by_charge.get(charge.id, 0)
                status, remaining = classify_paid_status(line.net_cents, paid)
                account_charges.append(
                    AccountCharge(
                        line=line,
                        paid_cents=paid,
                        remaining_cents=remaining,
                        status=status,
                    )
                )
            payments = (
                session.query(Payment)
                .filter(Payment.student_id == student_id)
                .order_by(Payment.paid_on.desc(), Payment.id.desc())
                .all()
            )
            credits = (
                session.query(Credit)
                .filter(Credit.student_id == student_id)
                .order_by(Credit.id.desc())
                .all()
            )

        outstanding = sum(c.remaining_cents for c in account_charges)
        credits_cents = sum(c.amount_cents for c in credits)
        return StudentAccount(
            student=student,
            charges=account_charges,
            payments=payments,
            credits=credits,
            outstanding_cents=outstanding,
            credits_cents=credits_cents,
            balance_cents=outstanding - credits_cents,
            received_cents=sum(p.amount_cents for p in payments),
        )

    def student_balance(self, student_id: int) -> Money:
        """The live balance: what is still owed after payments and credits."""
        return self.student_account(student_id).balance_cents

    def list_recent_payments(self, limit: int = 10) -> list[Payment]:
        """The most recent payments across all students, for the payments page."""
        with self._session() as session:
            return (
                session.query(Payment)
                .options(joinedload(Payment.student).joinedload(Student.school_class))
                .order_by(Payment.created_at.desc(), Payment.id.desc())
                .limit(limit)
                .all()
            )

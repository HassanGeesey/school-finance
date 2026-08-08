"""Payments & receipts service: recording money in, oldest-first allocation, credits.

Business rules only — the single testing seam. A payment (amount + method +
date) is recorded against a student and, in one transaction, is applied to the
oldest unpaid charges first (partial application supported); any excess becomes
a Credit on the student's account. The account view exposes charges with their
paid/remaining status, payments, credits, and the live balance. Every payment is
audited. Route concerns live in ``test_payments_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditActions, AuditError, AuditService
from app.classes.service import ClassService
from app.fees.service import AdjustmentsService, FeeService
from app.models import (
    AuditLogEntry,
    Charge,
    Credit,
    Payment,
    PaymentAllocation,
    User,
    UserRoles,
)
from app.payments.service import (
    ChargeStatus,
    InvalidMethod,
    PaymentError,
    PaymentNotFound,
    PaymentService,
)
from app.students.service import StudentNotFound, StudentService

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


@pytest.fixture()
def fees(db, audit) -> FeeService:
    return FeeService(db, audit=audit)


@pytest.fixture()
def adjustments(db, audit) -> AdjustmentsService:
    return AdjustmentsService(db, audit=audit)


@pytest.fixture()
def payments(db, audit) -> PaymentService:
    return PaymentService(db, audit=audit)


@pytest.fixture()
def admin(db, session) -> User:
    user = User(
        username="admin",
        name="Head Teacher",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
    )
    session.add(user)
    session.commit()
    return user


def make_billed_student(
    fees: FeeService,
    classes: ClassService,
    students: StudentService,
    admin: User,
    name: str = "Grade 1",
    items: tuple[tuple[str, str], ...] = (("Tuition", "50.00"),),
    months: tuple[int, ...] = (3,),
    year: int = 2026,
) -> tuple[int, int]:
    cls = classes.create_class(user=admin, name=name)
    for item_name, amount in items:
        classes.add_fee_item(user=admin, class_id=cls.id, name=item_name, amount=amount)
    student = students.add_student(user=admin, class_id=cls.id, first_name="Ada", last_name="Lovelace")
    for month in months:
        fees.generate(user=admin, class_id=cls.id, month=month, year=year)
    return student.id, cls.id


def student_charges(session, student_id: int) -> list[Charge]:
    return (
        session.query(Charge)
        .filter(Charge.student_id == student_id)
        .order_by(Charge.year, Charge.month, Charge.id)
        .all()
    )


def allocations_for(session, payment_id: int) -> list[PaymentAllocation]:
    return (
        session.query(PaymentAllocation)
        .filter(PaymentAllocation.payment_id == payment_id)
        .order_by(PaymentAllocation.id)
        .all()
    )


def payment_entries(session) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=AuditActions.PAYMENT_RECORD)
        .order_by(AuditLogEntry.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Recording a payment
# ---------------------------------------------------------------------------


def test_a_partial_payment_reduces_the_oldest_charge(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="30.00", method="cash", paid_on=date(2026, 8, 6)
    )

    assert payment.amount_cents == 3000
    assert payment.method == "cash"
    assert payment.student_id == student_id
    assert payment.recorded_by == admin.id
    (allocation,) = allocations_for(session, payment.id)
    charge = session.get(Charge, allocation.charge_id)
    assert charge.month == 3
    assert allocation.amount_cents == 3000
    assert session.query(Credit).count() == 0
    assert payments.student_balance(student_id) == 2000


def test_a_payment_clears_the_oldest_unpaid_charges_first(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )

    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )

    allocations = allocations_for(session, payment.id)
    assert len(allocations) == 2
    march, april = student_charges(session, student_id)
    assert allocations[0].charge_id == march.id
    assert allocations[0].amount_cents == 5000
    assert allocations[1].charge_id == april.id
    assert allocations[1].amount_cents == 1000
    assert payments.student_balance(student_id) == 4000


def test_a_payment_skips_charges_already_paid(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )

    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="10.00", method="bank", paid_on=date(2026, 8, 5)
    )

    march, april = student_charges(session, student_id)
    (allocation,) = allocations_for(session, payment.id)
    assert allocation.charge_id == april.id
    assert allocation.amount_cents == 1000
    assert payments.student_balance(student_id) == 4000


def test_an_overpayment_becomes_a_credit(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="70.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (allocation,) = allocations_for(session, payment.id)
    assert allocation.amount_cents == 5000
    (credit,) = session.query(Credit).all()
    assert credit.student_id == student_id
    assert credit.amount_cents == 2000
    assert credit.payment_id == payment.id
    account = payments.student_account(student_id)
    assert account.outstanding_cents == 0
    assert account.credits_cents == 2000
    assert account.balance_cents == -2000


def test_a_payment_with_no_charges_sits_entirely_as_credit(
    payments, classes, students, admin, session
):
    cls = classes.create_class(user=admin, name="Grade 1")
    student = students.add_student(user=admin, class_id=cls.id, first_name="Ada", last_name="Lovelace")

    payment = payments.record_payment(
        user=admin, student_id=student.id, amount="40.00", method="bank", paid_on=date(2026, 8, 6)
    )

    assert session.query(PaymentAllocation).count() == 0
    (credit,) = session.query(Credit).all()
    assert credit.amount_cents == 4000
    assert credit.payment_id == payment.id
    account = payments.student_account(student.id)
    assert account.balance_cents == -4000


def test_the_payment_method_is_recorded(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="10.00", method="bank", paid_on=date(2026, 8, 6)
    )

    assert payment.method == "bank"


def test_a_payment_can_be_recorded_without_an_actor(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payment = payments.record_payment(
        user=None, student_id=student_id, amount="10.00", method="cash", paid_on=date(2026, 8, 6)
    )

    assert payment.recorded_by is None
    assert payments.student_balance(student_id) == 4000


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_a_payment_requires_a_positive_amount(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="0", method="cash", paid_on=date(2026, 8, 6)
        )
    with pytest.raises(PaymentError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="-5.00", method="cash", paid_on=date(2026, 8, 6)
        )
    assert session.query(Payment).count() == 0


def test_a_payment_rejects_a_bad_amount(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="not-money", method="cash", paid_on=date(2026, 8, 6)
        )


def test_a_payment_translates_the_shared_amount_rule(
    payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError, match="Enter a valid amount"):
        payments.record_payment(
            user=admin, student_id=student_id, amount="not-money", method="cash", paid_on=date(2026, 8, 6)
        )
    with pytest.raises(PaymentError, match="greater than zero"):
        payments.record_payment(
            user=admin, student_id=student_id, amount="0", method="cash", paid_on=date(2026, 8, 6)
        )


def test_a_preview_translates_the_shared_amount_rule(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError, match="Enter a valid amount"):
        payments.preview_application(student_id, "not-money")
    with pytest.raises(PaymentError, match="greater than zero"):
        payments.preview_application(student_id, "0")


def test_a_payment_rejects_an_unknown_method(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(InvalidMethod):
        payments.record_payment(
            user=admin, student_id=student_id, amount="10.00", method="cheque", paid_on=date(2026, 8, 6)
        )


def test_a_payment_rejects_a_future_date(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="10.00", method="cash", paid_on=date(2100, 1, 1)
        )


def test_a_payment_rejects_a_missing_student(payments, admin):
    with pytest.raises(StudentNotFound):
        payments.record_payment(
            user=admin, student_id=999, amount="10.00", method="cash", paid_on=date(2026, 8, 6)
        )


# ---------------------------------------------------------------------------
# Account view
# ---------------------------------------------------------------------------


def test_account_lists_charges_with_paid_status(
    payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="10.00", method="cash", paid_on=date(2026, 8, 5)
    )

    account = payments.student_account(student_id)

    assert len(account.charges) == 2
    by_month = {line.charge.month: line for line in account.charges}
    assert by_month[3].paid_cents == 5000
    assert by_month[3].remaining_cents == 0
    assert by_month[3].status == ChargeStatus.PAID
    assert by_month[4].paid_cents == 1000
    assert by_month[4].remaining_cents == 4000
    assert by_month[4].status == ChargeStatus.PARTIAL


def test_account_marks_an_untouched_charge_unpaid(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )

    account = payments.student_account(student_id)

    for line in account.charges:
        assert line.status == ChargeStatus.UNPAID
        assert line.remaining_cents == 5000


def test_account_lists_payments_most_recent_first(
    payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="10.00", method="cash", paid_on=date(2026, 8, 1)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="5.00", method="bank", paid_on=date(2026, 8, 5)
    )

    account = payments.student_account(student_id)

    assert [p.amount_cents for p in account.payments] == [500, 1000]
    assert account.received_cents == 1500


def test_account_lists_credits(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )

    account = payments.student_account(student_id)

    assert len(account.credits) == 1
    assert account.credits[0].amount_cents == 1000
    assert account.credits_cents == 1000
    assert account.balance_cents == -1000


def test_balance_is_outstanding_minus_credits(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="30.00", method="cash", paid_on=date(2026, 8, 6)
    )

    account = payments.student_account(student_id)

    assert account.outstanding_cents == 7000
    assert account.credits_cents == 0
    assert account.balance_cents == 7000


def test_a_waiver_after_a_full_payment_never_makes_the_balance_negative(
    payments, adjustments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )
    charge = session.query(Charge).filter(Charge.student_id == student_id).one()
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Scholarship", amount="10.00")

    account = payments.student_account(student_id)

    assert account.charges[0].remaining_cents == 0
    assert account.balance_cents == 0


def test_get_payment_loads_allocations_and_student(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payment = payments.record_payment(
        user=admin, student_id=student_id, amount="25.00", method="cash", paid_on=date(2026, 8, 6)
    )

    loaded = payments.get_payment(payment.id)

    assert loaded.id == payment.id
    assert loaded.student.full_name == "Ada Lovelace"
    assert loaded.student.school_class.name == "Grade 1"
    assert len(loaded.allocations) == 1
    assert loaded.allocations[0].amount_cents == 2500
    assert loaded.allocations[0].charge.month == 3


def test_get_payment_raises_for_a_missing_payment(payments):
    with pytest.raises(PaymentNotFound):
        payments.get_payment(999)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_a_payment_is_audited(payments, fees, classes, students, admin, session):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payments.record_payment(
        user=admin, student_id=student_id, amount="30.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (entry,) = payment_entries(session)
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary
    assert "$30.00" in entry.summary
    assert "Cash" in entry.summary
    assert "2026-08-06" in entry.summary


def test_an_overpayment_mentions_the_credit_in_the_audit(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (entry,) = payment_entries(session)
    assert "credit" in entry.summary
    assert "$10.00" in entry.summary


def test_a_rejected_payment_writes_no_audit_entry(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="0", method="cash", paid_on=date(2026, 8, 6)
        )

    assert payment_entries(session) == []


def test_an_audit_failure_rolls_back_the_whole_payment(
    payments, fees, classes, students, admin, session
):
    """The audit entry lands in the same transaction as the payment, so a
    failure to audit must undo the payment too — nothing is recorded that
    isn't also audited."""
    student_id, _ = make_billed_student(fees, classes, students, admin)

    class BrokenAudit:
        def add(self, session, *, user, action, summary):
            raise AuditError("boom")

    payments._audit = BrokenAudit()  # type: ignore[assignment]

    with pytest.raises(AuditError):
        payments.record_payment(
            user=admin, student_id=student_id, amount="10.00", method="cash", paid_on=date(2026, 8, 6)
        )

    assert session.query(Payment).count() == 0
    assert session.query(PaymentAllocation).count() == 0
    assert session.query(Credit).count() == 0
    assert payment_entries(session) == []


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_preview_shows_oldest_first_allocation_without_writing(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )

    preview = payments.preview_application(student_id, "60.00")

    assert [(line.period_label, line.applied_cents) for line in preview.lines] == [
        ("March 2026", 5000),
        ("April 2026", 1000),
    ]
    assert preview.applied_cents == 6000
    assert preview.credit_cents == 0
    assert session.query(Payment).count() == 0


def test_preview_of_an_overpayment_shows_the_credit(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    preview = payments.preview_application(student_id, "70.00")

    assert [(line.period_label, line.applied_cents) for line in preview.lines] == [
        ("March 2026", 5000)
    ]
    assert preview.applied_cents == 5000
    assert preview.credit_cents == 2000


def test_preview_reflects_charges_already_partly_paid(
    payments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )

    preview = payments.preview_application(student_id, "20.00")

    assert [(line.period_label, line.applied_cents) for line in preview.lines] == [
        ("April 2026", 2000)
    ]
    assert preview.credit_cents == 0


def test_preview_rejects_an_invalid_amount(payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    with pytest.raises(PaymentError):
        payments.preview_application(student_id, "0")

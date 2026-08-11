"""Payment service: month-tagged recording and roll-forward credit (FW-15/16/21/22).

A payment is recorded against (student, month+year tag, amount, method, date) —
any month is recordable. It settles the tagged month's remaining shortfall; any
excess rolls forward as ``Credit`` (FW-15), consumed by the oldest owed months'
shortfalls first and visible per month (FW-21). The record screen's default tag
is the oldest unpaid owed month (FW-22-1); a tag outside the owed range warns,
rather than blocks (FW-22-2). Business rules only — route concerns live in
``test_payments_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassService
from app.fees.service import period_label
from app.models import AuditLogEntry, ClosedMonth, Credit, Payment, User, UserRoles
from app.payments.service import (
    InvalidDate,
    InvalidMethod,
    InvalidPeriod,
    PaymentError,
    PaymentService,
)
from app.students.service import StudentNotFound, StudentService

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def payments(db, audit) -> PaymentService:
    return PaymentService(db, audit=audit)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


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


def make_student(students, classes, admin, enrolled_on="2026-03-01"):
    """A student with a $50.00/month amount, enrolled March 2026 by default."""
    cls = classes.create_class(user=admin, name="Grade 1")
    return students.add_student(
        user=admin,
        class_id=cls.id,
        first_name="Ada",
        last_name="Lovelace",
        custom_amount=5000,
        enrolled_on=enrolled_on,
    )


def line_for(account, month, year):
    for line in account.lines:
        if line.month == month and line.year == year:
            return line
    return None


def payments_rows(session):
    return session.query(Payment).order_by(Payment.id).all()


def credits_rows(session):
    return session.query(Credit).order_by(Credit.id).all()


def audit_entries(session, action=AuditActions.PAYMENT_RECORD):
    return (
        session.query(AuditLogEntry)
        .filter_by(action=action)
        .order_by(AuditLogEntry.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Recording: the month tag (FW-16)
# ---------------------------------------------------------------------------


def test_record_payment_stores_the_tagged_month_and_other_fields(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payment = payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="30.00",
        method="bank",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    stored = session.query(Payment).one()
    assert stored.id == payment.id
    assert stored.student_id == student.id
    assert (stored.month, stored.year) == (3, 2026)
    assert stored.amount_cents == 3000
    assert stored.method == "bank"
    assert stored.paid_on == date(2026, 3, 5)
    assert stored.recorded_by == admin.id


def test_record_payment_applies_to_the_tagged_months_shortfall(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="30.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    account = payments.account_summary(student.id).account
    march = line_for(account, 3, 2026)
    assert march.paid_cents == 3000
    assert march.remaining_cents == 2000  # $50 expected − $30 paid
    assert credits_rows(session) == []


def test_excess_over_the_tagged_months_expected_becomes_credit_linked_to_payment(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payment = payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="60.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    (credit,) = credits_rows(session)
    assert credit.amount_cents == 1000
    assert credit.payment_id == payment.id
    account = payments.account_summary(student.id).account
    assert line_for(account, 3, 2026).remaining_cents == 0
    assert account.credits_cents == 1000


def test_any_month_is_recordable_including_one_before_enrollment(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="40.00",
        method="cash",
        paid_on="2026-01-15",
        month=1,
        year=2026,
    )

    (payment,) = payments_rows(session)
    assert (payment.month, payment.year) == (1, 2026)
    (credit,) = credits_rows(session)  # before enrollment → nothing owed → all credit
    assert credit.amount_cents == 4000


def test_a_payment_tagged_to_a_future_month_is_recorded_as_credit(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="40.00",
        method="cash",
        paid_on="2026-08-01",
        month=12,
        year=2026,
    )

    (payment,) = payments_rows(session)
    assert (payment.month, payment.year) == (12, 2026)
    (credit,) = credits_rows(session)
    assert credit.amount_cents == 4000  # outside the owed range → warning, not block


def test_a_payment_tagged_to_a_closed_month_becomes_credit(
    payments, students, classes, admin, session
):
    session.add(ClosedMonth(month=6, year=2026))
    session.commit()
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="40.00",
        method="cash",
        paid_on="2026-06-10",
        month=6,
        year=2026,
    )

    assert len(payments_rows(session)) == 1
    (credit,) = credits_rows(session)
    assert credit.amount_cents == 4000  # closed months carry no expected amount


# ---------------------------------------------------------------------------
# Preview (the live "expected vs paid vs credit" confirmation, nothing written)
# ---------------------------------------------------------------------------


def test_preview_shows_expected_paid_remaining_applied_and_credit(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    preview = payments.preview_application(student.id, 3, 2026, "60.00")

    assert preview.period_label == period_label(3, 2026)
    assert preview.expected_cents == 5000
    assert preview.paid_cents == 0
    assert preview.remaining_cents == 5000
    assert preview.applied_cents == 5000
    assert preview.credit_cents == 1000
    assert preview.in_owed_range is True
    assert payments_rows(session) == []  # a preview writes nothing


def test_preview_flags_months_outside_the_owed_range(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    preview = payments.preview_application(student.id, 12, 2026, "40.00")

    assert preview.expected_cents == 0
    assert preview.applied_cents == 0
    assert preview.credit_cents == 4000
    assert preview.in_owed_range is False
    assert payments_rows(session) == []


def test_preview_accounts_for_payments_already_tagged_to_the_month(
    payments, students, classes, admin
):
    student = make_student(students, classes, admin)
    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="30.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    preview = payments.preview_application(student.id, 3, 2026, "30.00")

    assert preview.paid_cents == 3000
    assert preview.remaining_cents == 2000
    assert preview.applied_cents == 2000
    assert preview.credit_cents == 1000


def test_preview_rejects_an_invalid_amount(payments, students, classes, admin):
    student = make_student(students, classes, admin)

    for bad in ("0", "-5.00", "not-a-number"):
        with pytest.raises(PaymentError):
            payments.preview_application(student.id, 3, 2026, bad)


# ---------------------------------------------------------------------------
# Roll-forward credit, consumed oldest owed month first (FW-21)
# ---------------------------------------------------------------------------


def test_credit_covers_the_oldest_owed_months_shortfalls_first(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    # $120 tagged to March against a $50 month: $50 applied, $70 carried.
    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="120.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    account = payments.account_summary(student.id).account
    march = line_for(account, 3, 2026)
    april = line_for(account, 4, 2026)
    may = line_for(account, 5, 2026)
    assert march.credit_consumed_cents == 0  # March is settled by its own payment
    assert april.credit_consumed_cents == 5000
    assert april.remaining_cents == 0
    assert may.credit_consumed_cents == 2000
    assert may.remaining_cents == 3000  # $70 − $50 consumed so far
    assert account.credits_cents == 7000


def test_overpayment_balance_reflects_credit_held_not_double_counted(
    payments, students, classes, admin, session
):
    today = date.today()
    student = make_student(
        students, classes, admin, enrolled_on=f"{today.year:04d}-{today.month:02d}-01"
    )

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="60.00",
        method="cash",
        paid_on=today.isoformat(),
        month=today.month,
        year=today.year,
    )

    account = payments.account_summary(student.id).account
    assert account.expected_cents == 5000
    assert account.received_cents == 6000
    assert account.credits_cents == 1000
    assert account.balance_cents == -1000  # net position: holding $10 credit
    assert account.owed_cents == 0


def test_balance_equals_expected_minus_received_across_months(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="60.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    account = payments.account_summary(student.id).account
    expected = 5000 * len(account.lines)
    assert account.received_cents == 6000
    assert account.balance_cents == expected - 6000
    assert account.owed_cents == max(expected - 6000, 0)


# ---------------------------------------------------------------------------
# Oldest unpaid owed month (FW-22-1): the record screen's default tag
# ---------------------------------------------------------------------------


def test_account_summary_surfaces_the_oldest_unpaid_month(
    payments, students, classes, admin
):
    student = make_student(students, classes, admin)

    assert payments.account_summary(student.id).oldest_unpaid == (2026, 3)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="30.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )
    assert payments.account_summary(student.id).oldest_unpaid == (2026, 3)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="30.00",
        method="cash",
        paid_on="2026-03-15",
        month=3,
        year=2026,
    )
    assert payments.account_summary(student.id).oldest_unpaid == (2026, 4)


def test_account_summary_oldest_unpaid_is_none_when_nothing_is_owed(
    payments, students, classes, admin
):
    today = date.today()
    student = make_student(
        students, classes, admin, enrolled_on=f"{today.year:04d}-{today.month:02d}-01"
    )

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="50.00",
        method="cash",
        paid_on=today.isoformat(),
        month=today.month,
        year=today.year,
    )

    assert payments.account_summary(student.id).oldest_unpaid is None


# ---------------------------------------------------------------------------
# Audit and atomicity
# ---------------------------------------------------------------------------


def test_record_payment_is_audited_with_month_applied_and_credit(
    payments, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    payments.record_payment(
        user=admin,
        student_id=student.id,
        amount="60.00",
        method="cash",
        paid_on="2026-03-05",
        month=3,
        year=2026,
    )

    (entry,) = audit_entries(session)
    assert entry.action == AuditActions.PAYMENT_RECORD
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary
    assert period_label(3, 2026) in entry.summary
    assert "$50.00 applied" in entry.summary
    assert "excess $10.00" in entry.summary


def test_a_rejected_payment_writes_nothing(payments, students, classes, admin, session):
    student = make_student(students, classes, admin)

    with pytest.raises(PaymentError, match="greater than zero"):
        payments.record_payment(
            user=admin,
            student_id=student.id,
            amount="0",
            method="cash",
            paid_on="2026-03-05",
            month=3,
            year=2026,
        )
    with pytest.raises(InvalidPeriod):
        payments.record_payment(
            user=admin,
            student_id=student.id,
            amount="10.00",
            method="cash",
            paid_on="2026-03-05",
            month=13,
            year=2026,
        )
    with pytest.raises(InvalidDate, match="future"):
        payments.record_payment(
            user=admin,
            student_id=student.id,
            amount="10.00",
            method="cash",
            paid_on="2100-01-01",
            month=3,
            year=2026,
        )
    with pytest.raises(InvalidMethod):
        payments.record_payment(
            user=admin,
            student_id=student.id,
            amount="10.00",
            method="cheque",
            paid_on="2026-03-05",
            month=3,
            year=2026,
        )
    with pytest.raises(StudentNotFound):
        payments.record_payment(
            user=admin,
            student_id=999,
            amount="10.00",
            method="cash",
            paid_on="2026-03-05",
            month=3,
            year=2026,
        )

    assert payments_rows(session) == []
    assert credits_rows(session) == []
    assert audit_entries(session) == []

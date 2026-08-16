"""Waiver service: per-(student, month) charge forgiveness (FW-10/FW-11/FW-13).

A waiver reduces a month's expected amount by a given amount, never below zero.
Multiple waivers stack on the same month; a reason is required; creation is
audited with who and why. Both Admin and Finance officer can waive (a service
has no role check — the route gate covers FW-13). Business rules only — route
concerns live in ``test_waivers_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassService
from app.fees.account import expected_cents, waivers_for_month
from app.fees.service import WaiverError, WaiverService, period_label
from app.models import AuditLogEntry, User, UserRoles, Waiver
from app.students.service import StudentService

PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _scoped(world):
    return world


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def waivers(db, audit) -> WaiverService:
    return WaiverService(db, audit=audit)


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


@pytest.fixture()
def finance(db, session) -> User:
    user = User(
        username="cashier",
        name="Cashier",
        password_hash=PASSWORD,
        role=UserRoles.FINANCE,
    )
    session.add(user)
    session.commit()
    return user


def make_student(students, classes, admin, first="Ada", last="Lovelace"):
    cls = classes.create_class(user=admin, name="Grade 1")
    return students.add_student(
        user=admin,
        class_id=cls.id,
        first_name=first,
        last_name=last,
        custom_amount=5000,
        enrolled_on="2026-03-01",
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_add_waiver_stores_period_amount_reason_and_actor(
    waivers, students, classes, admin, session
):
    student = make_student(students, classes, admin)

    created = waivers.add_waiver(
        user=admin, student_id=student.id, month=4, year=2026, amount="25.00", label="Mid-month partial"
    )

    stored = session.query(Waiver).one()
    assert stored.id == created.id
    assert (stored.month, stored.year) == (4, 2026)
    assert stored.amount_cents == 2500
    assert stored.label == "Mid-month partial"
    assert stored.created_by == admin.id


def test_add_waiver_accepts_a_decimal_amount(waivers, students, classes, admin):
    student = make_student(students, classes, admin)

    created = waivers.add_waiver(
        user=admin, student_id=student.id, month=4, year=2026, amount=12.5, label="Discount"
    )

    assert created.amount_cents == 1250


def test_add_waiver_requires_a_reason(waivers, students, classes, admin):
    student = make_student(students, classes, admin)

    with pytest.raises(WaiverError, match="reason"):
        waivers.add_waiver(
            user=admin, student_id=student.id, month=4, year=2026, amount="10.00", label=""
        )
    with pytest.raises(WaiverError, match="reason"):
        waivers.add_waiver(
            user=admin, student_id=student.id, month=4, year=2026, amount="10.00", label="   "
        )


def test_add_waiver_requires_a_positive_amount(waivers, students, classes, admin):
    student = make_student(students, classes, admin)

    for bad in ("0", "-5.00", "not-a-number"):
        with pytest.raises(WaiverError):
            waivers.add_waiver(
                user=admin, student_id=student.id, month=4, year=2026, amount=bad, label="Discount"
            )


def test_add_waiver_rejects_an_invalid_month(waivers, students, classes, admin):
    student = make_student(students, classes, admin)

    with pytest.raises(WaiverError, match="month"):
        waivers.add_waiver(user=admin, student_id=student.id, month=0, year=2026, amount="10.00", label="X")
    with pytest.raises(WaiverError, match="month"):
        waivers.add_waiver(user=admin, student_id=student.id, month=13, year=2026, amount="10.00", label="X")


def test_add_waiver_rejects_an_out_of_range_year(waivers, students, classes, admin):
    student = make_student(students, classes, admin)

    with pytest.raises(WaiverError, match="year"):
        waivers.add_waiver(user=admin, student_id=student.id, month=4, year=1999, amount="10.00", label="X")
    with pytest.raises(WaiverError, match="year"):
        waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2101, amount="10.00", label="X")


def test_add_waiver_rejects_an_unknown_student(waivers, admin):
    with pytest.raises(WaiverError, match="student"):
        waivers.add_waiver(user=admin, student_id=999, month=4, year=2026, amount="10.00", label="X")


# ---------------------------------------------------------------------------
# Stacking (FW-11) and the expected floor (FW-10)
# ---------------------------------------------------------------------------


def test_multiple_waivers_stack_on_the_same_month(waivers, students, classes, admin, session):
    student = make_student(students, classes, admin)

    waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2026, amount="20.00", label="Sibling discount")
    waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2026, amount="5.00", label="Good attendance")

    rows = session.query(Waiver).all()
    assert len(rows) == 2
    assert waivers_for_month(session, student.id, 4, 2026) == 2500


def test_a_waiver_reduces_the_months_expected(waivers, students, classes, admin, session):
    student = make_student(students, classes, admin)
    waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2026, amount="10.00", label="Partial")

    expected = expected_cents(session, student, 4, 2026, set(), date(2026, 4, 30))

    assert expected == 4000  # $50.00 monthly amount − $10.00 waiver


def test_stacked_waivers_floor_the_expected_at_zero(waivers, students, classes, admin, session):
    student = make_student(students, classes, admin)
    waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2026, amount="30.00", label="First")
    waivers.add_waiver(user=admin, student_id=student.id, month=4, year=2026, amount="40.00", label="Second")

    expected = expected_cents(session, student, 4, 2026, set(), date(2026, 4, 30))

    assert expected == 0  # 70.00 waived against a $50.00 amount never goes negative


# ---------------------------------------------------------------------------
# Audit (who + why, FW-13)
# ---------------------------------------------------------------------------


def test_add_waiver_is_audited_with_who_and_why(waivers, students, classes, admin, session):
    student = make_student(students, classes, admin)

    waivers.add_waiver(
        user=admin, student_id=student.id, month=4, year=2026, amount="25.00", label="Hardship"
    )

    entry = (
        session.query(AuditLogEntry).filter_by(action=AuditActions.WAIVER_ADD).one()
    )
    assert entry.action == AuditActions.WAIVER_ADD
    assert entry.user_id == admin.id
    assert student.full_name in entry.summary
    assert "Hardship" in entry.summary
    assert "$25.00" in entry.summary
    assert period_label(4, 2026) in entry.summary


def test_a_finance_officer_can_waive(waivers, students, classes, admin, finance, session):
    student = make_student(students, classes, admin)

    created = waivers.add_waiver(
        user=finance, student_id=student.id, month=4, year=2026, amount="50.00", label="Left early"
    )

    assert created.amount_cents == 5000
    entry = (
        session.query(AuditLogEntry).filter_by(action=AuditActions.WAIVER_ADD).one()
    )
    assert entry.user_id == finance.id

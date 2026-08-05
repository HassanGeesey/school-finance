"""Per-student month adjustments: extras and waivers on a monthly charge.

Business rules only — the single testing seam. An Admin adds an extra item to a
student's month (increases the charge) or applies a waiver/discount (decreases
it). The net charge is computed live as base + extras - waivers, so adjustments
reflect on the student's balance immediately. A waiver can never drive a charge
below zero. Every adjustment is audited. Finance officers cannot adjust — that
is enforced at the route layer in ``test_adjustments_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassService
from app.fees.service import AdjustmentError, AdjustmentsService, FeeService
from app.models import (
    Adjustment,
    AdjustmentKinds,
    AuditLogEntry,
    Charge,
    Class,
    ClassStatus,
    User,
    UserRoles,
)
from app.students.service import StudentService

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
    items: tuple[tuple[str, str], ...] = (("Tuition", "50.00"), ("Boarding", "12.50")),
) -> tuple[Class, int]:
    cls = classes.create_class(user=admin, name=name)
    for item_name, amount in items:
        classes.add_fee_item(user=admin, class_id=cls.id, name=item_name, amount=amount)
    student = students.add_student(user=admin, class_id=cls.id, first_name="Ada", last_name="Lovelace")
    fees.generate(user=admin, class_id=cls.id, month=3, year=2026)
    return cls, student.id


def first_charge(session, student_id: int) -> Charge:
    return session.query(Charge).filter(Charge.student_id == student_id).one()


def adjustment_entries(session) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=AuditActions.ADJUSTMENT_ADD)
        .order_by(AuditLogEntry.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Extras
# ---------------------------------------------------------------------------


def test_extra_increases_the_charge(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)
    assert charge.amount_cents == 6250

    adj = adjustments.add_extra(
        user=admin, charge_id=charge.id, label="Lunch", amount="3.50"
    )

    assert adj.kind == AdjustmentKinds.EXTRA
    assert adj.label == "Lunch"
    assert adj.amount_cents == 350
    line = adjustments.list_student_charges(student_id)[0]
    assert line.base_cents == 6250
    assert line.extras_cents == 350
    assert line.waivers_cents == 0
    assert line.net_cents == 6600


def test_extra_amounts_stack_on_the_same_charge(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")
    adjustments.add_extra(user=admin, charge_id=charge.id, label="Trip", amount="8.00")

    line = adjustments.list_student_charges(student_id)[0]
    assert line.extras_cents == 1000
    assert line.net_cents == 7250


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------


def test_waiver_reduces_the_charge(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adj = adjustments.apply_waiver(
        user=admin, charge_id=charge.id, label="Scholarship", amount="10.00"
    )

    assert adj.kind == AdjustmentKinds.WAIVER
    assert adj.label == "Scholarship"
    assert adj.amount_cents == 1000
    line = adjustments.list_student_charges(student_id)[0]
    assert line.waivers_cents == 1000
    assert line.net_cents == 5250


def test_extras_and_waivers_combine(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Hardship", amount="5.00")

    line = adjustments.list_student_charges(student_id)[0]
    assert line.extras_cents == 200
    assert line.waivers_cents == 500
    assert line.net_cents == 5950  # 6250 + 200 - 500


def test_waiver_cannot_drive_a_charge_below_zero(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    with pytest.raises(AdjustmentError):
        adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Too much", amount="70.00")

    assert adjustments.list_student_charges(student_id)[0].net_cents == 6250


def test_waiver_can_clear_the_charge_exactly(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Full waiver", amount="62.50")

    line = adjustments.list_student_charges(student_id)[0]
    assert line.net_cents == 0

    with pytest.raises(AdjustmentError):
        adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Any more", amount="0.01")


def test_a_waiver_counts_against_the_live_net_balance(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Partial", amount="60.00")

    with pytest.raises(AdjustmentError):
        adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Past zero", amount="4.60")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_adjustment_requires_a_label(adjustments, fees, classes, students, admin, session):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    with pytest.raises(AdjustmentError):
        adjustments.add_extra(user=admin, charge_id=charge.id, label="   ", amount="5.00")


def test_adjustment_requires_a_positive_amount(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    with pytest.raises(AdjustmentError):
        adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="0")
    with pytest.raises(AdjustmentError):
        adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Oops", amount="-5.00")


def test_adjustment_rejects_a_bad_amount(adjustments, fees, classes, students, admin, session):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    with pytest.raises(AdjustmentError):
        adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="not-money")


def test_adjusting_a_missing_charge_raises(adjustments, admin):
    with pytest.raises(AdjustmentError):
        adjustments.add_extra(user=admin, charge_id=999, label="Lunch", amount="5.00")
    with pytest.raises(AdjustmentError):
        adjustments.apply_waiver(user=admin, charge_id=999, label="Waiver", amount="5.00")


# ---------------------------------------------------------------------------
# Account listing & balance
# ---------------------------------------------------------------------------


def test_student_balance_is_the_sum_of_net_charges(
    adjustments, fees, classes, students, admin, session
):
    cls, student_id = make_billed_student(fees, classes, students, admin)
    fees.generate(user=admin, class_id=cls.id, month=4, year=2026)
    charges = session.query(Charge).order_by(Charge.month).all()
    assert adjustments.student_balance(student_id) == 12500

    adjustments.add_extra(user=admin, charge_id=charges[0].id, label="Lunch", amount="2.00")
    assert adjustments.student_balance(student_id) == 12700

    adjustments.apply_waiver(user=admin, charge_id=charges[1].id, label="Waiver", amount="12.50")
    assert adjustments.student_balance(student_id) == 12700 - 1250


def test_balance_reflects_an_adjustment_immediately(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)

    assert adjustments.student_balance(student_id) == 6250
    charge = first_charge(session, student_id)
    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="3.50")
    assert adjustments.student_balance(student_id) == 6600


def test_list_student_charges_returns_most_recent_period_first(
    adjustments, fees, classes, students, admin, session
):
    cls, student_id = make_billed_student(fees, classes, students, admin)
    fees.generate(user=admin, class_id=cls.id, month=4, year=2026)

    lines = adjustments.list_student_charges(student_id)

    assert [(line.charge.year, line.charge.month) for line in lines] == [(2026, 4), (2026, 3)]
    assert lines[0].period_label == "April 2026"
    assert lines[1].period_label == "March 2026"


def test_list_student_charges_includes_the_adjustment_rows(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)
    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")

    line = adjustments.list_student_charges(student_id)[0]

    assert len(line.adjustments) == 1
    assert line.adjustments[0].label == "Lunch"
    assert line.adjustments[0].amount_cents == 200


def test_adjusting_an_archived_students_charge_is_allowed(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    students.archive_student(user=admin, student_id=student_id)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")

    assert adjustments.list_student_charges(student_id)[0].net_cents == 6450


def test_list_student_charges_for_an_unknown_student_is_empty(adjustments):
    assert adjustments.list_student_charges(999) == []
    assert adjustments.student_balance(999) == 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_an_extra_is_audited(adjustments, fees, classes, students, admin, session):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="3.50")

    (entry,) = adjustment_entries(session)
    assert entry.user_id == admin.id
    assert "Ada Lovelace" in entry.summary
    assert "March 2026" in entry.summary
    assert "Lunch" in entry.summary
    assert "$3.50" in entry.summary


def test_a_waiver_is_audited(adjustments, fees, classes, students, admin, session):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Scholarship", amount="10.00")

    (entry,) = adjustment_entries(session)
    assert "Scholarship" in entry.summary
    assert "$10.00" in entry.summary


def test_a_rejected_adjustment_writes_no_audit_entry(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    with pytest.raises(AdjustmentError):
        adjustments.add_extra(user=admin, charge_id=charge.id, label="", amount="5.00")

    assert adjustment_entries(session) == []


def test_each_adjustment_writes_its_own_audit_entry(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=admin, charge_id=charge.id, label="Lunch", amount="2.00")
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Waiver", amount="1.00")

    entries = adjustment_entries(session)
    assert len(entries) == 2


def test_adjustments_are_created_without_an_actor(
    adjustments, fees, classes, students, admin, session
):
    _, student_id = make_billed_student(fees, classes, students, admin)
    charge = first_charge(session, student_id)

    adjustments.add_extra(user=None, charge_id=charge.id, label="Lunch", amount="2.00")

    assert session.query(Adjustment).count() == 1

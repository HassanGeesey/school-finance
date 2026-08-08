"""Payment-allocation planner: the one clearing rule.

Pure business rule tests for :mod:`app.payments.planner`. ``plan_application``
computes, for a given amount, how much clears each charge (oldest unpaid first,
partials supported) and what becomes a credit. ``paid_cents_by_charge`` is the
shared grouping used by recording, the account view, reports, and arrears — it
is tested once here.
"""

from datetime import date

import pytest

from app.audit.service import AuditService
from app.classes.service import ClassService
from app.fees.service import AdjustmentsService, FeeService
from app.models import Adjustment, AdjustmentKinds, Charge, User, UserRoles
from app.payments.planner import paid_cents_by_charge, plan_application
from app.payments.service import PaymentService
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
    months: tuple[int, ...] = (3,),
    year: int = 2026,
) -> int:
    cls = classes.create_class(user=admin, name="Grade 1")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")
    student = students.add_student(
        user=admin, class_id=cls.id, first_name="Ada", last_name="Lovelace"
    )
    for month in months:
        fees.generate(user=admin, class_id=cls.id, month=month, year=year)
    return student.id


# ---------------------------------------------------------------------------
# plan_application — pure allocation
# ---------------------------------------------------------------------------


def make_charge(
    charge_id: int,
    amount_cents: int,
    *,
    month: int = 3,
    adjustments: tuple[Adjustment, ...] = (),
) -> Charge:
    charge = Charge(
        id=charge_id,
        student_id=1,
        month=month,
        year=2026,
        amount_cents=amount_cents,
    )
    charge.adjustments = list(adjustments)
    return charge


def extra(amount_cents: int) -> Adjustment:
    return Adjustment(
        charge_id=0, kind=AdjustmentKinds.EXTRA, label="Late fee", amount_cents=amount_cents
    )


def waiver(amount_cents: int) -> Adjustment:
    return Adjustment(
        charge_id=0, kind=AdjustmentKinds.WAIVER, label="Scholarship", amount_cents=amount_cents
    )


def test_plan_clears_the_oldest_charge_first():
    march = make_charge(1, 5000, month=3)
    april = make_charge(2, 5000, month=4)

    applied, credit = plan_application([march, april], {}, 6000)

    assert applied == {1: 5000, 2: 1000}
    assert credit == 0


def test_plan_applies_partially_to_one_charge():
    march = make_charge(1, 5000)

    applied, credit = plan_application([march], {}, 3000)

    assert applied == {1: 3000}
    assert credit == 0


def test_plan_overpayment_becomes_credit():
    march = make_charge(1, 5000)

    applied, credit = plan_application([march], {}, 7000)

    assert applied == {1: 5000}
    assert credit == 2000


def test_plan_skips_charges_already_settled():
    march = make_charge(1, 5000, month=3)
    april = make_charge(2, 5000, month=4)

    applied, credit = plan_application([march, april], {1: 5000}, 4000)

    assert applied == {2: 4000}
    assert credit == 0


def test_plan_respects_the_charge_net_of_adjustments():
    charge = make_charge(
        1, 5000, adjustments=(extra(500), waiver(1000))
    )  # net 4500

    applied, credit = plan_application([charge], {}, 5000)

    assert applied == {1: 4500}
    assert credit == 500


def test_plan_skips_a_charge_waived_to_zero():
    charge = make_charge(1, 5000, adjustments=(waiver(5000),))  # net 0

    applied, credit = plan_application([charge], {}, 1000)

    assert applied == {}
    assert credit == 1000


def test_plan_with_no_charges_sits_entirely_as_credit():
    applied, credit = plan_application([], {}, 4000)

    assert applied == {}
    assert credit == 4000


# ---------------------------------------------------------------------------
# paid_cents_by_charge — the shared grouping
# ---------------------------------------------------------------------------


def test_paid_cents_grouping_sums_every_allocated_cent(
    session, payments, fees, classes, students, admin
):
    student_id = make_billed_student(fees, classes, students, admin, months=(3, 4))
    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )
    charges = (
        session.query(Charge).filter(Charge.student_id == student_id).all()
    )
    charge_ids = [charge.id for charge in charges]

    grouped = paid_cents_by_charge(session, charge_ids)

    assert grouped[charges[0].id] == 5000
    assert grouped[charges[1].id] == 1000


def test_paid_cents_grouping_filters_by_charge_ids(session, payments, fees, classes, students, admin):
    first = make_billed_student(fees, classes, students, admin)
    second = make_billed_student(fees, classes, students, admin, months=(4,))
    payments.record_payment(
        user=admin, student_id=first, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )
    payments.record_payment(
        user=admin, student_id=second, amount="10.00", method="cash", paid_on=date(2026, 8, 6)
    )
    first_charge = (
        session.query(Charge).filter(Charge.student_id == first).one()
    )
    second_charge = (
        session.query(Charge).filter(Charge.student_id == second).one()
    )

    grouped = paid_cents_by_charge(session, [first_charge.id])

    assert grouped == {first_charge.id: 5000}
    assert second_charge.id not in grouped


def test_paid_cents_grouping_with_no_ids_is_empty(session):
    assert paid_cents_by_charge(session, []) == {}


def test_paid_cents_grouping_with_no_filter_counts_everything(
    session, payments, fees, classes, students, admin
):
    first = make_billed_student(fees, classes, students, admin)
    second = make_billed_student(fees, classes, students, admin, months=(4,))
    payments.record_payment(
        user=admin, student_id=first, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )
    payments.record_payment(
        user=admin, student_id=second, amount="10.00", method="cash", paid_on=date(2026, 8, 6)
    )

    grouped = paid_cents_by_charge(session)

    assert grouped == {
        session.query(Charge).filter(Charge.student_id == first).one().id: 5000,
        session.query(Charge).filter(Charge.student_id == second).one().id: 1000,
    }

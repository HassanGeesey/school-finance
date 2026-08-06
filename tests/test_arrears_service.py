"""Arrears service: the outstanding-money report.

Business rules only — the single testing seam. A student is in arrears when
their unpaid charge balances exceed their credits; the report lists every such
student with how much they owe and how old the debt is (measured from the oldest
*unpaid* charge's period start). Archived students and Completed/Inactive
classes keep their arrears and still appear. Students with no outstanding
balance — fully paid, holding enough credit, or never billed — are excluded.
Route concerns live in ``test_arrears_routes.py``.
"""

from datetime import date

import pytest

from app.arrears.service import (
    AGE_BAND_CURRENT,
    AGE_BAND_LATE,
    AGE_BAND_OVERDUE,
    ArrearsService,
    debt_age_band,
)
from app.audit.service import AuditService
from app.classes.service import ClassService
from app.fees.service import AdjustmentsService, FeeService
from app.models import Charge, ClassStatus, StudentStatus, User, UserRoles
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
def arrears(db) -> ArrearsService:
    return ArrearsService(db)


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
    first_name: str = "Ada",
    last_name: str = "Lovelace",
) -> tuple[int, int]:
    cls = classes.create_class(user=admin, name=name)
    for item_name, amount in items:
        classes.add_fee_item(user=admin, class_id=cls.id, name=item_name, amount=amount)
    student = students.add_student(
        user=admin, class_id=cls.id, first_name=first_name, last_name=last_name
    )
    for month in months:
        fees.generate(user=admin, class_id=cls.id, month=month, year=year)
    return student.id, cls.id


# ---------------------------------------------------------------------------
# Balance = charges minus payments minus credits
# ---------------------------------------------------------------------------


def test_arrears_balance_is_charges_minus_payments(
    arrears, payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="30.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.owed_cents == 7000  # 2 x 5000 charges minus the 3000 paid


def test_credits_are_deducted_from_arrears(
    arrears, payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    # Overpay March: March (5000) is cleared and 1000 becomes a credit.
    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )
    # A new April charge (5000) lands on top of the carried credit.
    fees.generate(user=admin, class_id=_class_of(students, student_id), month=4, year=2026)

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.owed_cents == 4000  # 5000 outstanding minus 1000 credit


def _class_of(students, student_id: int) -> int:
    return students.get_student(student_id).class_id


# ---------------------------------------------------------------------------
# Report: amount owed and debt age
# ---------------------------------------------------------------------------


def test_report_lists_owing_students_with_amount_owed_and_debt_age(
    arrears, fees, classes, students, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)

    (line,) = arrears.arrears_report(today=date(2026, 4, 15))

    assert line.student.id == student_id
    assert line.student.full_name == "Ada Lovelace"
    assert line.class_name == "Grade 1"
    assert line.class_status == ClassStatus.ACTIVE
    assert line.student_status == StudentStatus.ACTIVE
    assert line.owed_cents == 5000
    assert line.oldest_period_label == "March 2026"
    assert line.oldest_period_start == date(2026, 3, 1)
    assert line.age_days == 45
    assert line.age_band == AGE_BAND_LATE


def test_report_orders_students_by_oldest_debt_first(
    arrears, fees, classes, students, admin
):
    make_billed_student(fees, classes, students, admin, name="Grade 1", months=(3,))
    make_billed_student(
        fees, classes, students, admin, name="Grade 2", months=(2,), first_name="Grace", last_name="Hopper"
    )

    lines = arrears.arrears_report(today=date(2026, 8, 6))

    assert [line.student.full_name for line in lines] == ["Grace Hopper", "Ada Lovelace"]
    assert lines[0].oldest_period_label == "February 2026"
    assert lines[1].oldest_period_label == "March 2026"


def test_owed_amounts_are_summed_in_the_report(
    arrears, payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(2, 3)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    # February (5000) is cleared, March (5000) takes the remaining 1000: 4000 owed.
    assert line.owed_cents == 4000
    assert line.oldest_period_label == "March 2026"


# ---------------------------------------------------------------------------
# Archived students and completed classes keep their arrears
# ---------------------------------------------------------------------------


def test_archived_students_still_show_their_arrears(
    arrears, students, fees, classes, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    students.archive_student(user=admin, student_id=student_id)

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.student_status == StudentStatus.INACTIVE
    assert line.owed_cents == 5000


def test_completed_classes_still_show_their_arrears(
    arrears, fees, classes, students, admin
):
    student_id, class_id = make_billed_student(fees, classes, students, admin)
    classes.update_class(user=admin, class_id=class_id, name="Grade 1", status=ClassStatus.COMPLETED)

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.class_status == ClassStatus.COMPLETED
    assert line.owed_cents == 5000


def test_inactive_classes_still_show_their_arrears(
    arrears, fees, classes, students, admin
):
    student_id, class_id = make_billed_student(fees, classes, students, admin)
    classes.update_class(user=admin, class_id=class_id, name="Grade 1", status=ClassStatus.INACTIVE)

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.class_status == ClassStatus.INACTIVE
    assert line.owed_cents == 5000


# ---------------------------------------------------------------------------
# Students with no outstanding balance are excluded
# ---------------------------------------------------------------------------


def test_fully_paid_students_are_excluded(arrears, payments, fees, classes, students, admin):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )

    assert arrears.arrears_report(today=date(2026, 8, 6)) == []


def test_students_holding_enough_credit_are_excluded(
    arrears, payments, fees, classes, students, admin
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="60.00", method="cash", paid_on=date(2026, 8, 6)
    )

    assert arrears.arrears_report(today=date(2026, 8, 6)) == []


def test_students_who_were_never_billed_are_excluded(arrears, classes, students, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    students.add_student(user=admin, class_id=cls.id, first_name="Ada", last_name="Lovelace")

    assert arrears.arrears_report(today=date(2026, 8, 6)) == []


# ---------------------------------------------------------------------------
# Adjustments change the reported arrears
# ---------------------------------------------------------------------------


def test_waivers_reduce_the_reported_arrears(
    arrears, adjustments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    charge = session.query(Charge).filter_by(student_id=student_id).one()
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Scholarship", amount="10.00")

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.owed_cents == 4000


def test_extras_increase_the_reported_arrears(
    arrears, adjustments, fees, classes, students, admin, session
):
    student_id, _ = make_billed_student(fees, classes, students, admin)
    charge = session.query(Charge).filter_by(student_id=student_id).one()
    adjustments.add_extra(user=admin, charge_id=charge.id, label="Late fee", amount="5.00")

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.owed_cents == 5500


# ---------------------------------------------------------------------------
# Debt age
# ---------------------------------------------------------------------------


def test_debt_age_ignores_paid_charges(
    arrears, payments, fees, classes, students, admin
):
    # March is fully paid; April (5000) is unpaid — the age comes from April.
    student_id, _ = make_billed_student(
        fees, classes, students, admin, months=(3, 4)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="50.00", method="cash", paid_on=date(2026, 8, 6)
    )

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.oldest_period_label == "April 2026"
    assert line.age_days == 127  # 2026-08-06 minus 2026-04-01


def test_age_days_defaults_to_today(arrears, fees, classes, students, admin):
    today = date.today()
    make_billed_student(
        fees, classes, students, admin, months=(today.month,), year=today.year
    )

    (line,) = arrears.arrears_report()

    assert line.age_days == today.day - 1  # period start is the 1st of the month
    assert line.age_band == AGE_BAND_CURRENT


# ---------------------------------------------------------------------------
# Age bands at the thresholds (amber > 30, red > 60)
# ---------------------------------------------------------------------------


def test_debt_age_band_thresholds():
    assert debt_age_band(0) == AGE_BAND_CURRENT
    assert debt_age_band(30) == AGE_BAND_CURRENT
    assert debt_age_band(31) == AGE_BAND_LATE
    assert debt_age_band(60) == AGE_BAND_LATE
    assert debt_age_band(61) == AGE_BAND_OVERDUE


def test_an_old_unpaid_debt_is_marked_overdue(arrears, fees, classes, students, admin):
    make_billed_student(fees, classes, students, admin, months=(1,), year=2026)

    (line,) = arrears.arrears_report(today=date(2026, 8, 6))

    assert line.age_days == 217
    assert line.age_band == AGE_BAND_OVERDUE

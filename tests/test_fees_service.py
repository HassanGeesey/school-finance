"""Fee generation service: monthly charges per student, duplicate-safe.

Business rules only — the single testing seam. A Finance officer (or Admin)
picks a Class or All classes + Month + Year; each active student gets one
monthly charge summing the class's fee items, with the item breakdown snapshotted
so later structure edits never rewrite history. Re-generating the same
class+month+year is refused. Completed/Inactive classes never generate. Every
generation is audited. Route concerns live in ``test_fees_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassNotFound, ClassService
from app.fees.service import (
    AlreadyGenerated,
    ClassNotActive,
    FeeService,
    InvalidPeriod,
    NoFeeItems,
)
from app.models import (
    AuditLogEntry,
    Charge,
    Class,
    ClassStatus,
    GenerationRecord,
    StudentStatus,
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


def make_class(
    classes: ClassService,
    students: StudentService,
    admin: User,
    name: str = "Grade 1",
    status: str = ClassStatus.ACTIVE,
    items: tuple[tuple[str, str], ...] = (("Tuition", "50.00"), ("Boarding", "12.50")),
    pupil_names: tuple[tuple[str, str], ...] = (("Ada", "Lovelace"), ("Grace", "Hopper")),
) -> Class:
    cls = classes.create_class(user=admin, name=name, status=status)
    for item_name, amount in items:
        classes.add_fee_item(user=admin, class_id=cls.id, name=item_name, amount=amount)
    for first, last in pupil_names:
        students.add_student(user=admin, class_id=cls.id, first_name=first, last_name=last)
    return cls


# ---------------------------------------------------------------------------
# Generate for one class
# ---------------------------------------------------------------------------


def test_generate_creates_one_charge_per_active_student(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin)

    result = fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    assert result.charges_created == 2
    charges = session.query(Charge).order_by(Charge.student_id).all()
    assert len(charges) == 2
    for charge in charges:
        assert charge.month == 3
        assert charge.year == 2026
        assert charge.amount_cents == 6250  # 50.00 + 12.50
        assert charge.breakdown == [
            {"name": "Tuition", "amount_cents": 5000},
            {"name": "Boarding", "amount_cents": 1250},
        ]


def test_generate_records_the_generation_for_duplicate_safety(
    fees, classes, students, admin, session
):
    grade1 = make_class(classes, students, admin)

    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    records = session.query(GenerationRecord).all()
    assert len(records) == 1
    assert records[0].class_id == grade1.id
    assert records[0].month == 3
    assert records[0].year == 2026


def test_generate_result_reports_class_and_totals(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)

    result = fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    assert result.class_id == grade1.id
    assert result.month == 3
    assert result.year == 2026
    (line,) = result.generated
    assert line.class_name == "Grade 1"
    assert line.charges_created == 2
    assert line.per_student_cents == 6250
    assert line.total_cents == 12500
    assert result.total_cents == 12500


def test_generate_skips_archived_students(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin)
    archived = students.list_students(grade1.id)[0]
    students.archive_student(user=admin, student_id=archived.id)

    result = fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    assert result.charges_created == 1
    assert session.query(Charge).count() == 1


def test_generate_can_run_for_a_class_without_students(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin, pupil_names=())

    result = fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    assert result.charges_created == 0
    assert session.query(Charge).count() == 0
    assert session.query(GenerationRecord).count() == 1


def test_generate_snapshots_the_breakdown_at_generation_time(
    fees, classes, students, admin, session
):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)
    tuition = classes.class_summary(grade1.id).items[0].id
    classes.update_fee_item(user=admin, class_id=grade1.id, item_id=tuition, name="Tuition", amount="99.00")

    charges = session.query(Charge).order_by(Charge.id).all()
    assert len(charges) == 2
    charge = charges[0]
    assert charge.amount_cents == 6250
    assert charge.breakdown == [
        {"name": "Tuition", "amount_cents": 5000},
        {"name": "Boarding", "amount_cents": 1250},
    ]


def test_regenerating_the_same_class_and_month_is_refused(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    with pytest.raises(AlreadyGenerated):
        fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    assert session.query(Charge).count() == 2  # never doubled


def test_the_same_class_can_be_generated_for_a_different_month(
    fees, classes, students, admin, session
):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    result = fees.generate(user=admin, class_id=grade1.id, month=4, year=2026)

    assert result.charges_created == 2
    assert session.query(Charge).count() == 4


# ---------------------------------------------------------------------------
# Generate for all classes
# ---------------------------------------------------------------------------


def test_generate_all_bills_every_active_class(fees, classes, students, admin, session):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    make_class(classes, students, admin, name="Grade 2", items=(("Tuition", "80.00"),))

    result = fees.generate(user=admin, class_id=None, month=3, year=2026)

    assert {line.class_name for line in result.generated} == {"Grade 1", "Grade 2"}
    assert result.charges_created == 4
    assert {r.class_id for r in session.query(GenerationRecord).all()} == {
        line.class_id for line in result.generated
    }
    amounts = {charge.amount_cents for charge in session.query(Charge).all()}
    assert amounts == {5000, 8000}


def test_generate_all_excludes_completed_and_inactive_classes(
    fees, classes, students, admin, session
):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    make_class(
        classes, students, admin, name="Grade 8", status=ClassStatus.COMPLETED, items=(("Tuition", "90.00"),)
    )
    make_class(
        classes, students, admin, name="Paused", status=ClassStatus.INACTIVE, items=(("Tuition", "70.00"),)
    )

    result = fees.generate(user=admin, class_id=None, month=3, year=2026)

    assert [line.class_name for line in result.generated] == ["Grade 1"]
    assert session.query(Charge).count() == 2
    assert session.query(GenerationRecord).count() == 1


def test_generate_all_skips_active_classes_without_fee_items(
    fees, classes, students, admin, session
):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    make_class(classes, students, admin, name="Grade 2", items=())

    result = fees.generate(user=admin, class_id=None, month=3, year=2026)

    assert [line.class_name for line in result.generated] == ["Grade 1"]
    assert session.query(GenerationRecord).count() == 1
    assert any("Grade 2" in message and "fee items" in message for message in result.skipped)


def test_generate_all_skips_classes_already_generated_for_the_month(
    fees, classes, students, admin, session
):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    grade2 = make_class(classes, students, admin, name="Grade 2", items=(("Tuition", "80.00"),))
    fees.generate(user=admin, class_id=grade2.id, month=3, year=2026)

    result = fees.generate(user=admin, class_id=None, month=3, year=2026)

    assert [line.class_name for line in result.generated] == ["Grade 1"]
    assert any("Grade 2" in message and "already generated" in message for message in result.skipped)
    assert session.query(Charge).count() == 4  # 2 original + 2 new, nothing doubled


def test_generate_all_with_everything_already_generated_is_a_no_op(
    fees, classes, students, admin, session
):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    result = fees.generate(user=admin, class_id=None, month=3, year=2026)

    assert result.generated == []
    assert len(result.skipped) == 1
    assert session.query(Charge).count() == 2


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_generation_is_audited(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin)

    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_GENERATE).one()
    assert entry.user_id == admin.id
    assert "March" in entry.summary
    assert "2026" in entry.summary
    assert "Grade 1" in entry.summary
    assert "2" in entry.summary


def test_generation_of_all_classes_is_audited_once(fees, classes, students, admin, session):
    make_class(classes, students, admin, name="Grade 1")
    make_class(classes, students, admin, name="Grade 2")

    fees.generate(user=admin, class_id=None, month=3, year=2026)

    entries = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_GENERATE).all()
    assert len(entries) == 1
    assert "2 classes" in entries[0].summary
    assert "4 charge(s)" in entries[0].summary


def test_a_no_op_generation_writes_no_audit_entry(fees, classes, students, admin, session):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    fees.generate(user=admin, class_id=None, month=3, year=2026)

    entries = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_GENERATE).all()
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_generate_rejects_an_invalid_month(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)

    with pytest.raises(InvalidPeriod):
        fees.generate(user=admin, class_id=grade1.id, month=0, year=2026)
    with pytest.raises(InvalidPeriod):
        fees.generate(user=admin, class_id=grade1.id, month=13, year=2026)


def test_generate_rejects_an_unreasonable_year(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)

    with pytest.raises(InvalidPeriod):
        fees.generate(user=admin, class_id=grade1.id, month=3, year=1999)
    with pytest.raises(InvalidPeriod):
        fees.generate(user=admin, class_id=grade1.id, month=3, year=2200)


def test_generate_missing_class_raises(fees, admin):
    with pytest.raises(ClassNotFound):
        fees.generate(user=admin, class_id=999, month=3, year=2026)


def test_generate_refuses_a_completed_class(fees, classes, students, admin):
    grade8 = make_class(classes, students, admin, name="Grade 8", status=ClassStatus.COMPLETED)

    with pytest.raises(ClassNotActive):
        fees.generate(user=admin, class_id=grade8.id, month=3, year=2026)


def test_generate_refuses_an_inactive_class(fees, classes, students, admin):
    paused = make_class(classes, students, admin, name="Paused", status=ClassStatus.INACTIVE)

    with pytest.raises(ClassNotActive):
        fees.generate(user=admin, class_id=paused.id, month=3, year=2026)


def test_generate_refuses_a_class_without_fee_items(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin, items=())

    with pytest.raises(NoFeeItems):
        fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)


# ---------------------------------------------------------------------------
# Preview (confirm-dialog breakdown)
# ---------------------------------------------------------------------------


def test_preview_shows_the_breakdown_for_a_single_class(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)

    preview = fees.preview(class_id=grade1.id, month=3, year=2026)

    assert preview.class_id == grade1.id
    assert preview.class_name == "Grade 1"
    (line,) = preview.lines
    assert line.class_name == "Grade 1"
    assert line.student_count == 2
    assert line.per_student_cents == 6250
    assert line.total_cents == 12500
    assert line.skip_reason is None
    assert preview.total_cents == 12500


def test_preview_for_all_lists_each_active_class(fees, classes, students, admin):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    make_class(classes, students, admin, name="Grade 2", items=(("Tuition", "80.00"),))

    preview = fees.preview(class_id=None, month=3, year=2026)

    assert {line.class_name for line in preview.lines} == {"Grade 1", "Grade 2"}
    assert preview.class_name is None


def test_preview_for_all_excludes_completed_and_inactive_classes(fees, classes, students, admin):
    make_class(classes, students, admin, name="Grade 1", items=(("Tuition", "50.00"),))
    make_class(
        classes, students, admin, name="Grade 8", status=ClassStatus.COMPLETED, items=(("Tuition", "90.00"),)
    )
    make_class(
        classes, students, admin, name="Paused", status=ClassStatus.INACTIVE, items=(("Tuition", "70.00"),)
    )

    preview = fees.preview(class_id=None, month=3, year=2026)

    assert [line.class_name for line in preview.lines] == ["Grade 1"]


def test_preview_flags_a_class_already_generated(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)
    fees.generate(user=admin, class_id=grade1.id, month=3, year=2026)

    preview = fees.preview(class_id=grade1.id, month=3, year=2026)

    assert preview.lines[0].skip_reason is not None
    assert "already generated" in preview.lines[0].skip_reason


def test_preview_flags_a_non_active_class(fees, classes, students, admin):
    grade8 = make_class(classes, students, admin, name="Grade 8", status=ClassStatus.COMPLETED)

    preview = fees.preview(class_id=grade8.id, month=3, year=2026)

    assert preview.lines[0].skip_reason is not None


def test_preview_flags_a_class_without_fee_items(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin, items=())

    preview = fees.preview(class_id=grade1.id, month=3, year=2026)

    assert preview.lines[0].skip_reason is not None
    assert "fee items" in preview.lines[0].skip_reason


def test_preview_rejects_an_invalid_period(fees, classes, students, admin):
    grade1 = make_class(classes, students, admin)

    with pytest.raises(InvalidPeriod):
        fees.preview(class_id=grade1.id, month=0, year=2026)
    with pytest.raises(InvalidPeriod):
        fees.preview(class_id=None, month=3, year=2101)


def test_preview_missing_class_raises(fees, admin):
    with pytest.raises(ClassNotFound):
        fees.preview(class_id=999, month=3, year=2026)

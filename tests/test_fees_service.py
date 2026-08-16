"""Fee template service: Admin-managed named monthly amounts (FW-7, FW-19, FW-20).

Business rules only — the single testing seam. Templates are created, renamed,
and archived; an amount change is effective-dated (default next month, never
past) and propagates to every linked student via one ``StudentAmountChange``
row per student at the effective month. Every change is audited. Route concerns
live in ``test_fees_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassService
from app.fees.service import (
    ClosedMonthError,
    ClosedMonthService,
    DuplicateClosedMonth,
    InvalidPeriod,
    TemplateError,
    TemplateNotFound,
    TemplateService,
    default_effective_month,
    period_label,
)
from app.models import (
    AuditLogEntry,
    ClosedMonth,
    StudentAmountChange,
    User,
    UserRoles,
)
from app.students.service import StudentService

PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _scoped(world):
    return world


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def templates(db, audit) -> TemplateService:
    return TemplateService(db, audit=audit)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


@pytest.fixture()
def closed_months(db, audit) -> ClosedMonthService:
    return ClosedMonthService(db, audit=audit)


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


def make_template(templates, admin, name="Standard", amount="100.00"):
    return templates.create_template(user=admin, name=name, amount=amount)


def linked_student(students, classes, admin, template_id, first="Ada", last="Lovelace"):
    cls = classes.create_class(user=admin, name="Grade 1")
    return students.add_student(
        user=admin,
        class_id=cls.id,
        first_name=first,
        last_name=last,
        fee_template_id=template_id,
    )


def a_past_month() -> tuple[int, int]:
    today = date.today()
    if today.month == 1:
        return 12, today.year - 1
    return today.month - 1, today.year


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_template_stores_name_and_integer_cents(templates, admin, session):
    template = templates.create_template(user=admin, name="Standard", amount="50.00")

    from app.models import FeeTemplate

    stored = session.query(FeeTemplate).one()
    assert stored.id == template.id
    assert stored.name == "Standard"
    assert stored.amount_cents == 5000
    assert isinstance(stored.amount_cents, int)
    assert stored.archived is False


def test_create_template_accepts_a_decimal_amount(templates, admin):
    template = templates.create_template(user=admin, name="Boarding", amount=12.5)

    assert template.amount_cents == 1250


def test_create_template_requires_a_name(templates, admin):
    with pytest.raises(TemplateError):
        templates.create_template(user=admin, name="", amount="50.00")
    with pytest.raises(TemplateError):
        templates.create_template(user=admin, name="   ", amount="50.00")


def test_create_template_requires_a_positive_amount(templates, admin):
    with pytest.raises(TemplateError):
        templates.create_template(user=admin, name="Standard", amount="0")
    with pytest.raises(TemplateError):
        templates.create_template(user=admin, name="Standard", amount="-5.00")
    with pytest.raises(TemplateError):
        templates.create_template(user=admin, name="Standard", amount="not-a-number")


def test_create_template_translates_the_shared_amount_rule(templates, admin):
    with pytest.raises(TemplateError, match="Enter a valid amount"):
        templates.create_template(user=admin, name="Standard", amount="not-a-number")
    with pytest.raises(TemplateError, match="greater than zero"):
        templates.create_template(user=admin, name="Standard", amount="0")
    with pytest.raises(TemplateError, match="greater than zero"):
        templates.create_template(user=admin, name="Standard", amount="-5.00")


def test_create_template_is_audited(templates, admin, session):
    templates.create_template(user=admin, name="Standard", amount="100.00")

    entry = session.query(AuditLogEntry).one()
    assert entry.action == AuditActions.TEMPLATE_CREATE
    assert entry.user_id == admin.id
    assert "Standard" in entry.summary
    assert "$100.00" in entry.summary


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def test_get_template_returns_the_matching_template(templates, admin):
    template = make_template(templates, admin)

    assert templates.get_template(template.id).name == "Standard"


def test_get_template_missing_raises(templates, admin):
    with pytest.raises(TemplateNotFound):
        templates.get_template(999)


def test_list_templates_puts_active_first_then_archived_by_name(templates, admin, session):
    zeta = templates.create_template(user=admin, name="Zeta", amount="10.00")
    alpha = templates.create_template(user=admin, name="Alpha", amount="20.00")
    templates.archive_template(user=admin, template_id=zeta.id)
    archived = templates.create_template(user=admin, name="Old", amount="30.00")
    templates.archive_template(user=admin, template_id=archived.id)

    names = [template.name for template in templates.list_templates()]

    assert names == ["Alpha", "Old", "Zeta"]


def test_list_active_templates_excludes_archived(templates, admin):
    keep = make_template(templates, admin, name="Keep")
    drop = make_template(templates, admin, name="Drop")
    templates.archive_template(user=admin, template_id=drop.id)

    active = templates.list_active_templates()

    assert [template.id for template in active] == [keep.id]


def test_linked_student_counts_groups_by_template(templates, classes, students, admin):
    first = make_template(templates, admin, name="Standard")
    second = make_template(templates, admin, name="Boarding")
    linked_student(students, classes, admin, first.id, "Ada", "Lovelace")
    linked_student(students, classes, admin, first.id, "Grace", "Hopper")
    linked_student(students, classes, admin, second.id, "Alan", "Turing")

    assert templates.linked_student_counts() == {first.id: 2, second.id: 1}


def test_linked_student_counts_is_empty_with_no_links(templates, admin):
    assert templates.linked_student_counts() == {}


# ---------------------------------------------------------------------------
# Update (rename + effective-dated amount change, FW-19/FW-20)
# ---------------------------------------------------------------------------


def test_update_template_renames_and_audits(templates, admin, session):
    template = make_template(templates, admin, name="Standard")

    templates.update_template(
        user=admin, template_id=template.id, name="Standard Plus", amount="100.00"
    )

    template = templates.get_template(template.id)
    assert template.name == "Standard Plus"
    assert template.amount_cents == 10000  # untouched
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.TEMPLATE_RENAME).one()
    assert entry.user_id == admin.id
    assert "Standard" in entry.summary
    assert "Standard Plus" in entry.summary


def test_update_template_amount_change_updates_amount_and_audits(templates, admin, session):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=next_month,
        year=next_year,
    )

    template = templates.get_template(template.id)
    assert template.amount_cents == 12000
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.TEMPLATE_AMOUNT_CHANGE).one()
    assert entry.user_id == admin.id
    assert "$120.00" in entry.summary
    assert period_label(next_month, next_year) in entry.summary


def test_update_template_amount_change_propagates_to_linked_students(
    templates, classes, students, admin, session
):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    ada = linked_student(students, classes, admin, template.id, "Ada", "Lovelace")
    grace = linked_student(students, classes, admin, template.id, "Grace", "Hopper")
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=next_month,
        year=next_year,
    )

    rows = session.query(StudentAmountChange).all()
    assert len(rows) == 4  # one enrollment baseline per student + one propagation
    effective = [
        row for row in rows if (row.month, row.year) == (next_month, next_year)
    ]
    assert {row.student_id for row in effective} == {ada.id, grace.id}
    assert all(row.amount_cents == 12000 for row in effective)


def test_update_template_amount_change_skips_students_not_linked_to_it(
    templates, classes, students, admin, session
):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    other = make_template(templates, admin, name="Boarding", amount="200.00")
    linked_student(students, classes, admin, other.id)
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=next_month,
        year=next_year,
    )

    effective = [
        row
        for row in session.query(StudentAmountChange).all()
        if (row.month, row.year) == (next_month, next_year)
    ]
    assert len(effective) == 0  # the other template's students are untouched


def test_update_template_amount_change_defaults_to_next_month(
    templates, classes, students, admin, session
):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    linked_student(students, classes, admin, template.id)
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin, template_id=template.id, name="Standard", amount="150.00"
    )

    effective = [
        row
        for row in session.query(StudentAmountChange).all()
        if (row.month, row.year) == (next_month, next_year)
    ]
    assert len(effective) == 1
    assert effective[0].amount_cents == 15000


def test_update_template_amount_change_in_place_for_the_same_month(
    templates, classes, students, admin, session
):
    """A second change for the same effective month updates, never stacks (FW-20)."""
    template = make_template(templates, admin, name="Standard", amount="100.00")
    linked_student(students, classes, admin, template.id)
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=next_month,
        year=next_year,
    )
    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="130.00",
        month=next_month,
        year=next_year,
    )

    effective = [
        row
        for row in session.query(StudentAmountChange).all()
        if (row.month, row.year) == (next_month, next_year)
    ]
    assert len(effective) == 1  # the same month was updated, never stacked
    assert effective[0].amount_cents == 13000


def test_update_template_amount_changes_stack_across_months(
    templates, classes, students, admin, session
):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    linked_student(students, classes, admin, template.id)
    today = date.today()
    first = (today.month, today.year)  # the current month is allowed
    second = default_effective_month()  # the next calendar month — always distinct

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=first[0],
        year=first[1],
    )
    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="130.00",
        month=second[0],
        year=second[1],
    )

    rows = session.query(StudentAmountChange).all()
    assert len(rows) == 2
    assert {row.amount_cents for row in rows} == {12000, 13000}


def test_update_template_without_any_change_writes_no_audit(templates, admin, session):
    template = make_template(templates, admin, name="Standard", amount="100.00")

    templates.update_template(
        user=admin, template_id=template.id, name="Standard", amount="100.00"
    )

    assert session.query(AuditLogEntry).count() == 1  # only the creation


def test_update_template_renames_and_changes_amount_in_one_unit(
    templates, admin, session
):
    template = make_template(templates, admin, name="Standard", amount="100.00")
    next_month, next_year = default_effective_month()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Premium",
        amount="150.00",
        month=next_month,
        year=next_year,
    )

    actions = {
        entry.action for entry in session.query(AuditLogEntry).all()
    }
    assert AuditActions.TEMPLATE_RENAME in actions
    assert AuditActions.TEMPLATE_AMOUNT_CHANGE in actions


# ---------------------------------------------------------------------------
# Effective-month validation (FW-20: past months are frozen)
# ---------------------------------------------------------------------------


def test_update_template_rejects_an_invalid_month(templates, admin):
    template = make_template(templates, admin)

    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", month=0, year=2030
        )
    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", month=13, year=2030
        )


def test_update_template_rejects_an_out_of_range_year(templates, admin):
    template = make_template(templates, admin)

    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", month=3, year=1999
        )
    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", month=3, year=2101
        )


def test_update_template_requires_both_month_and_year(templates, admin):
    template = make_template(templates, admin)

    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", month=3
        )
    with pytest.raises(InvalidPeriod):
        templates.update_template(
            user=admin, template_id=template.id, name="Standard", amount="120.00", year=2030
        )


def test_update_template_rejects_a_past_effective_month(templates, admin):
    template = make_template(templates, admin)
    past_month, past_year = a_past_month()

    with pytest.raises(InvalidPeriod, match="past"):
        templates.update_template(
            user=admin,
            template_id=template.id,
            name="Standard",
            amount="120.00",
            month=past_month,
            year=past_year,
        )


def test_update_template_allows_the_current_month(templates, admin, session):
    template = make_template(templates, admin)
    today = date.today()

    templates.update_template(
        user=admin,
        template_id=template.id,
        name="Standard",
        amount="120.00",
        month=today.month,
        year=today.year,
    )

    assert templates.get_template(template.id).amount_cents == 12000
    assert session.query(AuditLogEntry).filter_by(action=AuditActions.TEMPLATE_AMOUNT_CHANGE).count() == 1


def test_update_template_missing_template_raises(templates, admin):
    with pytest.raises(TemplateNotFound):
        templates.update_template(
            user=admin, template_id=999, name="Standard", amount="100.00"
        )


# ---------------------------------------------------------------------------
# Archive / restore (no hard deletes)
# ---------------------------------------------------------------------------


def test_archive_template_marks_it_and_audits(templates, admin, session):
    template = make_template(templates, admin)

    templates.archive_template(user=admin, template_id=template.id)

    assert templates.get_template(template.id).archived is True
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.TEMPLATE_ARCHIVE).one()
    assert entry.user_id == admin.id
    assert "Standard" in entry.summary


def test_archive_template_keeps_linkage_and_history(templates, classes, students, admin, session):
    template = make_template(templates, admin)
    student = linked_student(students, classes, admin, template.id)

    templates.archive_template(user=admin, template_id=template.id)

    student = students.get_student(student.id)
    assert student.fee_template_id == template.id
    assert templates.linked_student_counts() == {template.id: 1}


def test_archiving_an_archived_template_is_a_no_op(templates, admin, session):
    template = make_template(templates, admin)
    templates.archive_template(user=admin, template_id=template.id)
    before = session.query(AuditLogEntry).count()

    templates.archive_template(user=admin, template_id=template.id)

    assert session.query(AuditLogEntry).count() == before


def test_restore_template_undoes_archival_and_audits(templates, admin, session):
    template = make_template(templates, admin)
    templates.archive_template(user=admin, template_id=template.id)

    templates.restore_template(user=admin, template_id=template.id)

    assert templates.get_template(template.id).archived is False
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.TEMPLATE_RESTORE).one()
    assert "Standard" in entry.summary


def test_restoring_a_live_template_is_a_no_op(templates, admin, session):
    template = make_template(templates, admin)
    before = session.query(AuditLogEntry).count()

    templates.restore_template(user=admin, template_id=template.id)

    assert session.query(AuditLogEntry).count() == before


def test_archiving_a_missing_template_raises(templates, admin):
    with pytest.raises(TemplateNotFound):
        templates.archive_template(user=admin, template_id=999)


# ---------------------------------------------------------------------------
# Closed months (FW-17): add / remove, unique per month+year, audited
# ---------------------------------------------------------------------------


def test_add_closed_month_stores_month_year_and_audits(closed_months, admin, session):
    closed_months.add_closed_month(user=admin, month=7, year=2026)

    stored = session.query(ClosedMonth).one()
    assert stored.month == 7
    assert stored.year == 2026
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.CLOSED_MONTH_ADD).one()
    assert entry.user_id == admin.id
    assert "July 2026" in entry.summary


def test_add_closed_month_is_idempotent_by_month_and_year(closed_months, admin, session):
    closed_months.add_closed_month(user=admin, month=7, year=2026)

    with pytest.raises(DuplicateClosedMonth):
        closed_months.add_closed_month(user=admin, month=7, year=2026)

    assert session.query(ClosedMonth).count() == 1


def test_add_closed_month_rejects_an_invalid_month(closed_months, admin):
    with pytest.raises(ClosedMonthError):
        closed_months.add_closed_month(user=admin, month=13, year=2026)
    with pytest.raises(ClosedMonthError):
        closed_months.add_closed_month(user=admin, month=None, year=2026)


def test_add_closed_month_rejects_an_out_of_range_year(closed_months, admin):
    with pytest.raises(ClosedMonthError):
        closed_months.add_closed_month(user=admin, month=1, year=1900)


def test_remove_closed_month_deletes_and_audits(closed_months, admin, session):
    closed_months.add_closed_month(user=admin, month=7, year=2026)

    closed_months.remove_closed_month(user=admin, month=7, year=2026)

    assert session.query(ClosedMonth).count() == 0
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.CLOSED_MONTH_REMOVE).one()
    assert entry.user_id == admin.id
    assert "July 2026" in entry.summary


def test_remove_closed_month_missing_raises(closed_months, admin):
    with pytest.raises(ClosedMonthError):
        closed_months.remove_closed_month(user=admin, month=7, year=2026)


def test_list_closed_months_orders_newest_first(closed_months, admin):
    closed_months.add_closed_month(user=admin, month=1, year=2026)
    closed_months.add_closed_month(user=admin, month=12, year=2025)
    closed_months.add_closed_month(user=admin, month=3, year=2026)

    rows = closed_months.list_closed_months()

    assert [(row.month, row.year) for row in rows] == [(3, 2026), (1, 2026), (12, 2025)]


def test_closed_month_set_returns_lookup_pairs(closed_months, admin):
    closed_months.add_closed_month(user=admin, month=7, year=2026)

    assert closed_months.closed_month_set() == {(7, 2026)}

"""Class service: creating/updating classes and their default fee template (FW-7).

Business rules only — the single testing seam. Every change is audited; no change
is a hard delete. A class carries an optional default :class:`FeeTemplate` that
fixes its monthly fee per student; setting/clearing it is audited. Route concerns
live in ``test_classes_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import ClassError, ClassNotFound, ClassService
from app.fees.service import TemplateService
from app.models import AuditLogEntry, Class, ClassStatus, Student, User, UserRoles

PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _scoped(world):
    return world


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def templates(db, audit) -> TemplateService:
    return TemplateService(db, audit=audit)


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


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_class_defaults_to_active(classes, session):
    cls = classes.create_class(user=None, name="Grade 1")

    row = session.query(Class).one()
    assert row.id == cls.id
    assert row.name == "Grade 1"
    assert row.status == ClassStatus.ACTIVE
    assert row.default_template_id is None


def test_create_class_accepts_an_explicit_status(classes, session):
    classes.create_class(user=None, name="Grade 8", status=ClassStatus.COMPLETED)

    assert session.query(Class).one().status == ClassStatus.COMPLETED


def test_create_class_requires_a_name(classes):
    with pytest.raises(ClassError):
        classes.create_class(user=None, name="")
    with pytest.raises(ClassError):
        classes.create_class(user=None, name="   ")


def test_create_class_rejects_an_unknown_status(classes):
    with pytest.raises(ClassError):
        classes.create_class(user=None, name="Grade 1", status="frozen")


def test_create_class_is_audited(classes, admin, session):
    classes.create_class(user=admin, name="Grade 1")

    entry = session.query(AuditLogEntry).one()
    assert entry.action == AuditActions.CLASS_CREATE
    assert entry.user_id == admin.id
    assert "Grade 1" in entry.summary


def test_create_class_links_the_default_template(classes, templates, admin, session):
    template = make_template(templates, admin)

    cls = classes.create_class(
        user=admin, name="Grade 1", default_template_id=template.id
    )

    assert session.query(Class).one().default_template_id == template.id
    assert cls.default_template_id == template.id


def test_create_class_rejects_a_missing_template(classes, admin):
    with pytest.raises(ClassError):
        classes.create_class(user=admin, name="Grade 1", default_template_id=999)


def test_create_class_rejects_an_archived_template(classes, templates, admin):
    template = make_template(templates, admin)
    templates.archive_template(user=admin, template_id=template.id)

    with pytest.raises(ClassError, match="valid fee template"):
        classes.create_class(
            user=admin, name="Grade 1", default_template_id=template.id
        )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_class_renames(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.update_class(user=admin, class_id=cls.id, name="Grade One", status=ClassStatus.ACTIVE)

    row = session.query(Class).one()
    assert row.name == "Grade One"
    assert row.status == ClassStatus.ACTIVE


def test_update_class_changes_status(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.update_class(
        user=admin, class_id=cls.id, name="Grade 1", status=ClassStatus.INACTIVE
    )

    assert session.query(Class).one().status == ClassStatus.INACTIVE


def test_update_class_reopens_a_completed_class(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 8", status=ClassStatus.COMPLETED)

    classes.update_class(
        user=admin, class_id=cls.id, name="Grade 8", status=ClassStatus.ACTIVE
    )

    assert session.query(Class).one().status == ClassStatus.ACTIVE


def test_update_class_requires_a_name(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(ClassError):
        classes.update_class(user=admin, class_id=cls.id, name="", status=ClassStatus.ACTIVE)


def test_update_class_rejects_an_unknown_status(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(ClassError):
        classes.update_class(user=admin, class_id=cls.id, name="Grade 1", status="archived")


def test_update_class_missing_class_raises(classes, admin):
    with pytest.raises(ClassNotFound):
        classes.update_class(user=admin, class_id=999, name="Grade 1", status=ClassStatus.ACTIVE)


def test_update_class_audits_a_rename(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.update_class(user=admin, class_id=cls.id, name="Grade One", status=ClassStatus.ACTIVE)

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.CLASS_RENAME).one()
    assert entry.user_id == admin.id
    assert "Grade 1" in entry.summary
    assert "Grade One" in entry.summary


def test_update_class_audits_a_status_change(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.update_class(
        user=admin, class_id=cls.id, name="Grade 1", status=ClassStatus.COMPLETED
    )

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.CLASS_STATUS).one()
    assert "Grade 1" in entry.summary
    assert "Completed" in entry.summary


def test_update_class_without_change_writes_no_audit(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.update_class(user=admin, class_id=cls.id, name="Grade 1", status=ClassStatus.ACTIVE)

    assert session.query(AuditLogEntry).count() == 1  # only the creation entry


# ---------------------------------------------------------------------------
# Default fee template (FW-7)
# ---------------------------------------------------------------------------


def test_set_default_template_links_and_audits(classes, templates, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    template = make_template(templates, admin, name="Standard")

    classes.set_default_template(user=admin, class_id=cls.id, default_template_id=template.id)

    assert session.query(Class).one().default_template_id == template.id
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.CLASS_DEFAULT_TEMPLATE).one()
    assert entry.user_id == admin.id
    assert "Grade 1" in entry.summary
    assert "Standard" in entry.summary


def test_set_default_template_can_change_the_template(classes, templates, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    first = make_template(templates, admin, name="Standard")
    second = make_template(templates, admin, name="Premium")

    classes.set_default_template(user=admin, class_id=cls.id, default_template_id=first.id)
    classes.set_default_template(user=admin, class_id=cls.id, default_template_id=second.id)

    assert session.query(Class).one().default_template_id == second.id
    entries = session.query(AuditLogEntry).filter_by(action=AuditActions.CLASS_DEFAULT_TEMPLATE).all()
    assert len(entries) == 2


def test_set_default_template_clears_and_audits(classes, templates, admin, session):
    template = make_template(templates, admin)
    cls = classes.create_class(user=admin, name="Grade 1", default_template_id=template.id)

    classes.set_default_template(user=admin, class_id=cls.id, default_template_id=None)

    assert session.query(Class).one().default_template_id is None
    entry = (
        session.query(AuditLogEntry)
        .filter_by(action=AuditActions.CLASS_DEFAULT_TEMPLATE)
        .order_by(AuditLogEntry.id.desc())
        .first()
    )
    assert "Cleared" in entry.summary
    assert "Standard" in entry.summary


def test_set_default_template_to_the_same_choice_is_a_no_op(classes, templates, admin, session):
    template = make_template(templates, admin)
    cls = classes.create_class(user=admin, name="Grade 1", default_template_id=template.id)
    before = session.query(AuditLogEntry).count()

    classes.set_default_template(user=admin, class_id=cls.id, default_template_id=template.id)

    assert session.query(AuditLogEntry).count() == before


def test_set_default_template_rejects_a_missing_template(classes, templates, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    make_template(templates, admin)

    with pytest.raises(ClassError):
        classes.set_default_template(user=admin, class_id=cls.id, default_template_id=999)


def test_set_default_template_rejects_an_archived_template(classes, templates, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    template = make_template(templates, admin)
    templates.archive_template(user=admin, template_id=template.id)

    with pytest.raises(ClassError, match="valid fee template"):
        classes.set_default_template(user=admin, class_id=cls.id, default_template_id=template.id)
    assert session.query(Class).one().default_template_id is None


def test_set_default_template_missing_class_raises(classes, templates, admin):
    template = make_template(templates, admin)

    with pytest.raises(ClassNotFound):
        classes.set_default_template(user=admin, class_id=999, default_template_id=template.id)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def test_class_summary_reports_student_count_and_default_amount(
    classes, templates, admin, session
):
    template = make_template(templates, admin, amount="75.00")
    cls = classes.create_class(user=admin, name="Grade 1", default_template_id=template.id)
    for first, last in [("Ada", "Lovelace"), ("Grace", "Hopper")]:
        session.add(
            Student(first_name=first, last_name=last, class_id=cls.id, campus_id=cls.campus_id)
        )
    session.commit()

    summary = classes.class_summary(cls.id)

    assert summary.cls.id == cls.id
    assert summary.student_count == 2
    assert summary.monthly_total_cents == 7500
    assert summary.cls.default_template.name == "Standard"


def test_class_summary_without_a_default_template_reports_zero(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    summary = classes.class_summary(cls.id)

    assert summary.monthly_total_cents == 0
    assert summary.cls.default_template is None


def test_list_class_summaries_returns_all_in_creation_order(classes, admin):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")

    rows = classes.list_class_summaries()
    assert [c.cls.id for c in rows] == [first.id, second.id]


def test_list_class_summaries_uses_each_default_template_amount(
    classes, templates, admin
):
    low = make_template(templates, admin, name="Low", amount="50.00")
    high = make_template(templates, admin, name="High", amount="80.00")
    first = classes.create_class(user=admin, name="Grade 1", default_template_id=low.id)
    second = classes.create_class(user=admin, name="Grade 2", default_template_id=high.id)
    classes.create_class(user=admin, name="Grade 3")

    rows = classes.list_class_summaries()

    totals = {row.cls.id: row.monthly_total_cents for row in rows}
    assert totals[first.id] == 5000
    assert totals[second.id] == 8000
    assert totals[rows[2].cls.id] == 0


def test_get_class_returns_the_matching_class(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    assert classes.get_class(cls.id).name == "Grade 1"


def test_get_class_missing_raises(classes):
    with pytest.raises(ClassNotFound):
        classes.get_class(999)


def test_student_counts_groups_students_by_class(classes, session):
    first = classes.create_class(user=None, name="Grade 1")
    second = classes.create_class(user=None, name="Grade 2")
    for first_name, last_name, class_id in [
        ("Ada", "Lovelace", first.id),
        ("Grace", "Hopper", first.id),
        ("Alan", "Turing", second.id),
    ]:
        session.add(
            Student(
                first_name=first_name,
                last_name=last_name,
                class_id=class_id,
                campus_id=first.campus_id,
            )
        )
    session.commit()

    assert classes.student_counts() == {first.id: 2, second.id: 1}


def test_student_counts_is_empty_with_no_students(classes):
    assert classes.student_counts() == {}

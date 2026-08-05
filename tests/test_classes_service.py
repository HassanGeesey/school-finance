"""Class service: creating/updating classes and their itemized fee structures.

Business rules only — the single testing seam. Every change is audited; no change
is a hard delete (a class is created/renamed/reopened; fee items are removed but
their snapshots in already-generated charges are untouched). Route concerns live
in ``test_classes_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.classes.service import (
    ClassError,
    ClassNotFound,
    ClassService,
    DuplicateFeeItemName,
    FeeItemNotFound,
)
from app.models import AuditLogEntry, Class, ClassStatus, FeeItem, User, UserRoles

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


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


def test_create_class_defaults_to_active(classes, session):
    cls = classes.create_class(user=None, name="Grade 1")

    row = session.query(Class).one()
    assert row.id == cls.id
    assert row.name == "Grade 1"
    assert row.status == ClassStatus.ACTIVE


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


def test_list_class_summaries_returns_all_in_creation_order(classes, admin):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")

    rows = classes.list_class_summaries()
    assert [c.cls.id for c in rows] == [first.id, second.id]


def test_class_summary_reports_items_and_monthly_total(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Boarding", amount="12.50")

    summary = classes.class_summary(cls.id)

    assert summary.cls.id == cls.id
    assert summary.item_count == 2
    assert summary.monthly_total_cents == 6250
    assert [item.name for item in summary.items] == ["Tuition", "Boarding"]


def test_list_class_summaries_aggregates_each_class_separately(classes, admin):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")
    classes.add_fee_item(user=admin, class_id=first.id, name="Tuition", amount="50.00")
    classes.add_fee_item(user=admin, class_id=second.id, name="Tuition", amount="80.00")

    rows = classes.list_class_summaries()

    assert {row.cls.id: row.monthly_total_cents for row in rows} == {
        first.id: 5000,
        second.id: 8000,
    }


def test_get_class_returns_the_matching_class(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    assert classes.get_class(cls.id).name == "Grade 1"


def test_get_class_missing_raises(classes):
    with pytest.raises(ClassNotFound):
        classes.get_class(999)


def test_add_fee_item_stores_integer_cents(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    row = session.query(FeeItem).one()
    assert row.id == item.id
    assert row.class_id == cls.id
    assert row.name == "Tuition"
    assert row.amount_cents == 5000


def test_add_fee_item_accepts_a_decimal_amount(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Boarding", amount=12.5)

    assert item.amount_cents == 1250


def test_add_fee_item_requires_a_name(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(ClassError):
        classes.add_fee_item(user=admin, class_id=cls.id, name="", amount="50.00")


def test_add_fee_item_requires_a_positive_amount(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(ClassError):
        classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="0")
    with pytest.raises(ClassError):
        classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="-5.00")
    with pytest.raises(ClassError):
        classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="not-a-number")


def test_add_fee_item_rejects_a_duplicate_name_in_the_class(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    with pytest.raises(DuplicateFeeItemName):
        classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="60.00")
    assert session.query(FeeItem).count() == 1


def test_fee_item_name_uniqueness_matches_the_database_collation(classes, admin, session):
    """The DB constraint is case-sensitive; the app check mirrors it exactly."""
    cls = classes.create_class(user=admin, name="Grade 1")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    item = classes.add_fee_item(user=admin, class_id=cls.id, name="tuition", amount="60.00")

    assert item.amount_cents == 6000
    assert session.query(FeeItem).count() == 2


def test_add_fee_item_allows_same_name_in_another_class(classes, admin):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")

    classes.add_fee_item(user=admin, class_id=first.id, name="Tuition", amount="50.00")
    item = classes.add_fee_item(user=admin, class_id=second.id, name="Tuition", amount="80.00")

    assert item.amount_cents == 8000


def test_add_fee_item_missing_class_raises(classes, admin):
    with pytest.raises(ClassNotFound):
        classes.add_fee_item(user=admin, class_id=999, name="Tuition", amount="50.00")


def test_add_fee_item_is_audited(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")

    classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_ITEM_ADD).one()
    assert entry.user_id == admin.id
    assert "Tuition" in entry.summary
    assert "Grade 1" in entry.summary


def test_update_fee_item_changes_name_and_price(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    classes.update_fee_item(
        user=admin, class_id=cls.id, item_id=item.id, name="Tuition Fee", amount="55.50"
    )

    row = session.query(FeeItem).one()
    assert row.name == "Tuition Fee"
    assert row.amount_cents == 5550


def test_update_fee_item_requires_a_positive_amount(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    with pytest.raises(ClassError):
        classes.update_fee_item(
            user=admin, class_id=cls.id, item_id=item.id, name="Tuition", amount="0"
        )


def test_update_fee_item_rejects_a_duplicate_name(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    tuition = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")
    classes.add_fee_item(user=admin, class_id=cls.id, name="Boarding", amount="30.00")

    with pytest.raises(DuplicateFeeItemName):
        classes.update_fee_item(
            user=admin, class_id=cls.id, item_id=tuition.id, name="Boarding", amount="50.00"
        )


def test_update_fee_item_keeps_its_own_name(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")
    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    updated = classes.update_fee_item(
        user=admin, class_id=cls.id, item_id=item.id, name="Tuition", amount="60.00"
    )

    assert updated.name == "Tuition"
    assert updated.amount_cents == 6000


def test_update_fee_item_missing_item_raises(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(FeeItemNotFound):
        classes.update_fee_item(
            user=admin, class_id=cls.id, item_id=999, name="Tuition", amount="50.00"
        )


def test_update_fee_item_rejects_an_item_from_another_class(classes, admin, session):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")
    item = classes.add_fee_item(user=admin, class_id=second.id, name="Tuition", amount="80.00")

    with pytest.raises(FeeItemNotFound):
        classes.update_fee_item(
            user=admin, class_id=first.id, item_id=item.id, name="Tuition", amount="90.00"
        )
    assert session.query(FeeItem).one().amount_cents == 8000


def test_update_fee_item_audits_old_and_new_values(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    classes.update_fee_item(
        user=admin, class_id=cls.id, item_id=item.id, name="Tuition", amount="60.00"
    )

    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_ITEM_UPDATE).one()
    assert entry.user_id == admin.id
    assert "Grade 1" in entry.summary
    assert "Tuition ($50.00)" in entry.summary
    assert "Tuition ($60.00)" in entry.summary


def test_remove_fee_item_deletes_and_audits(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    item = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")

    classes.remove_fee_item(user=admin, class_id=cls.id, item_id=item.id)

    assert session.query(FeeItem).count() == 0
    entry = session.query(AuditLogEntry).filter_by(action=AuditActions.FEE_ITEM_REMOVE).one()
    assert entry.user_id == admin.id
    assert "Tuition" in entry.summary
    assert "Grade 1" in entry.summary


def test_remove_fee_item_missing_item_raises(classes, admin):
    cls = classes.create_class(user=admin, name="Grade 1")

    with pytest.raises(FeeItemNotFound):
        classes.remove_fee_item(user=admin, class_id=cls.id, item_id=999)


def test_remove_fee_item_rejects_an_item_from_another_class(classes, admin, session):
    first = classes.create_class(user=admin, name="Grade 1")
    second = classes.create_class(user=admin, name="Grade 2")
    item = classes.add_fee_item(user=admin, class_id=second.id, name="Tuition", amount="80.00")

    with pytest.raises(FeeItemNotFound):
        classes.remove_fee_item(user=admin, class_id=first.id, item_id=item.id)
    assert session.query(FeeItem).count() == 1


def test_removing_an_item_leaves_other_items_untouched(classes, admin, session):
    cls = classes.create_class(user=admin, name="Grade 1")
    tuition = classes.add_fee_item(user=admin, class_id=cls.id, name="Tuition", amount="50.00")
    boarding = classes.add_fee_item(user=admin, class_id=cls.id, name="Boarding", amount="30.00")

    classes.remove_fee_item(user=admin, class_id=cls.id, item_id=tuition.id)

    remaining = session.query(FeeItem).one()
    assert remaining.id == boarding.id

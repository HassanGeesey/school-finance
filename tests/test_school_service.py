"""School Dashboard service (multi-school ticket 08): Campus lifecycle, Owner
accounts, and per-Campus KPI cards.

Business rules only — the single testing seam. Route concerns live in
``test_school_routes.py``. Every operation resolves the School from the acting
scope's ``school_id``, so tests run under a School-scoped context.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.arrears.service import ArrearsService
from app.audit.service import AuditActions, AuditService
from app.reports.service import ReportService
from app.models import AuditLogEntry, Campus, School, User, UserRoles
from app.schools.service import (
    CampusNotFound,
    LastActiveCampus,
    SchoolDashboardService,
    SchoolError,
    UsernameTaken,
)
from app.tenants.scope import RequestScope, scope_context
from tests.helpers import add_payment, make_billed_student

PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def school_world(db):
    with db.session() as session:
        school = School(name="Sunrise Schools")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="Campus A")
        session.add(campus)
        session.commit()
        scope_ = RequestScope(user=None, school_id=school.id, campus_id=None)
    with scope_context(scope_):
        yield scope_


@pytest.fixture()
def service(db):
    return SchoolDashboardService(db, audit=AuditService(db), reports=None)


@pytest.fixture()
def actor(db, school_world):
    with db.session() as session:
        school = session.query(School).one()
        user = User(
            name="Super",
            username="super",
            password_hash="x",
            role=UserRoles.SUPERADMIN,
            school_id=school.id,
        )
        session.add(user)
        session.commit()
        return user


def audit_entries(db, action: str) -> list[AuditLogEntry]:
    with db.session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_list_campuses_orders_active_first_then_by_name(service, actor):
    service.create_campus(actor=actor, name="Zeta")
    service.create_campus(actor=actor, name="Alpha")
    service.create_campus(actor=actor, name="Beta")
    archived = service.create_campus(actor=actor, name="Closed")
    service.archive_campus(actor=actor, campus_id=archived.id)

    summaries = service.list_campuses()

    # The implicit "Campus A" (active) sorts among the other active names.
    assert [s.campus.name for s in summaries] == [
        "Alpha",
        "Beta",
        "Campus A",
        "Zeta",
        "Closed",
    ]
    assert all(s.campus.archived is False for s in summaries[:-1])
    assert summaries[-1].campus.name == "Closed"


def test_get_campus_returns_only_school_campuses(service, actor):
    service.create_campus(actor=actor, name="A")

    with pytest.raises(CampusNotFound):
        service.get_campus(999)


def test_list_owners_orders_active_first(service, actor):
    service.create_owner(actor=actor, name="Zed Board", username="zed", password=PASSWORD)
    service.create_owner(actor=actor, name="Ann Board", username="ann", password=PASSWORD)
    disabled = service.create_owner(actor=actor, name="Bob Board", username="bob", password=PASSWORD)
    service.disable_owner(actor=actor, user_id=disabled.id)

    owners = service.list_owners()

    assert [o.username for o in owners] == ["ann", "zed", "bob"]


# ---------------------------------------------------------------------------
# Campus lifecycle
# ---------------------------------------------------------------------------


def test_create_campus_creates_a_campus_and_audits(service, actor, db):
    campus = service.create_campus(actor=actor, name="Sunrise Branch", phone="+1 555")

    assert campus.id is not None
    assert campus.phone == "+1 555"
    assert campus.archived is False
    (entry,) = audit_entries(db, AuditActions.CAMPUS_CREATE)
    assert "Sunrise Branch" in entry.summary
    assert entry.campus_id is None  # school-level (MD-2)


def test_create_campus_requires_a_name(service, actor):
    with pytest.raises(SchoolError):
        service.create_campus(actor=actor, name="  ")


def test_create_campus_with_admin_creates_a_campus_bound_admin(service, actor, db):
    campus = service.create_campus(
        actor=actor,
        name="Branch",
        admin_name="Jane Head",
        admin_username="jane",
        admin_password=PASSWORD,
    )

    with db.session() as session:
        admin = (
            session.query(User)
            .filter_by(username="jane")
            .one()
        )
    assert admin.role == UserRoles.ADMIN
    assert admin.campus_id == campus.id
    assert admin.school_id == campus.school_id
    assert len(audit_entries(db, AuditActions.CAMPUS_ADMIN_ASSIGN)) == 1


def test_create_campus_admin_fields_are_all_or_none(service, actor):
    with pytest.raises(SchoolError):
        service.create_campus(
            actor=actor, name="Branch", admin_name="Jane", admin_username="jane"
        )


def test_create_campus_with_admin_rejects_a_duplicate_username(service, actor):
    service.create_owner(actor=actor, name="Jane", username="jane", password=PASSWORD)

    with pytest.raises(UsernameTaken):
        service.create_campus(
            actor=actor,
            name="Branch",
            admin_name="Jane",
            admin_username="jane",
            admin_password=PASSWORD,
        )


def test_create_owner_rejects_a_username_taken_by_a_campus_admin(service, actor):
    campus = service.create_campus(
        actor=actor,
        name="Branch",
        admin_name="Bob",
        admin_username="bob",
        admin_password=PASSWORD,
    )
    assert campus.id is not None

    with pytest.raises(UsernameTaken):
        service.create_owner(actor=actor, name="Bob", username="bob", password=PASSWORD)


def test_assign_campus_admin_later(service, actor, db):
    campus = service.create_campus(actor=actor, name="Branch")
    admin = service.create_campus_admin(
        actor=actor, campus_id=campus.id, name="Jane", username="jane", password=PASSWORD
    )

    assert admin.role == UserRoles.ADMIN
    assert admin.campus_id == campus.id
    assert len(audit_entries(db, AuditActions.CAMPUS_ADMIN_ASSIGN)) == 1


def test_cannot_assign_admin_to_an_archived_campus(service, actor):
    campus = service.create_campus(actor=actor, name="Branch")
    service.archive_campus(actor=actor, campus_id=campus.id)

    with pytest.raises(SchoolError):
        service.create_campus_admin(
            actor=actor, campus_id=campus.id, name="Jane", username="jane", password=PASSWORD
        )


def test_archive_campus_soft_deletes_and_audits(service, actor, db):
    campus = service.create_campus(actor=actor, name="Branch")
    service.create_campus(actor=actor, name="Other")

    archived = service.archive_campus(actor=actor, campus_id=campus.id)

    assert archived.archived is True
    with db.session() as session:
        assert session.get(Campus, campus.id).archived is True
    (entry,) = audit_entries(db, AuditActions.CAMPUS_ARCHIVE)
    assert entry.campus_id is None


def test_the_last_active_campus_cannot_be_archived(service, actor):
    only = service.create_campus(actor=actor, name="Only")
    # Archive every other campus first so "Only" becomes the last active one.
    for summary in service.list_campuses():
        if summary.campus.id != only.id and not summary.campus.archived:
            service.archive_campus(actor=actor, campus_id=summary.campus.id)

    with pytest.raises(LastActiveCampus):
        service.archive_campus(actor=actor, campus_id=only.id)


# ---------------------------------------------------------------------------
# Owner accounts
# ---------------------------------------------------------------------------


def test_create_owner_creates_a_school_bound_account(service, actor, db):
    owner = service.create_owner(actor=actor, name="The Board", username="board", password=PASSWORD)

    with db.session() as session:
        stored = session.get(User, owner.id)
    assert stored.role == UserRoles.OWNER
    assert stored.school_id is not None
    assert stored.campus_id is None
    (entry,) = audit_entries(db, AuditActions.OWNER_CREATE)
    assert "board" in entry.summary
    assert entry.campus_id is None


def test_create_owner_requires_fields_and_unique_username(service, actor):
    service.create_owner(actor=actor, name="Board", username="board", password=PASSWORD)
    with pytest.raises(SchoolError):
        service.create_owner(actor=actor, name="", username="x", password=PASSWORD)
    with pytest.raises(UsernameTaken):
        service.create_owner(actor=actor, name="Other", username="BOARD", password=PASSWORD)


def test_disable_and_enable_owner(service, actor, db):
    owner = service.create_owner(actor=actor, name="Board", username="board", password=PASSWORD)

    disabled = service.disable_owner(actor=actor, user_id=owner.id)
    assert disabled.is_active is False
    assert len(audit_entries(db, AuditActions.OWNER_DISABLE)) == 1

    enabled = service.enable_owner(actor=actor, user_id=owner.id)
    assert enabled.is_active is True
    assert len(audit_entries(db, AuditActions.OWNER_ENABLE)) == 1


def test_disable_owner_requires_an_owner_target(service, actor):
    from app.schools.service import OwnerNotFound

    campus = service.create_campus(actor=actor, name="Branch")
    admin = service.create_campus_admin(
        actor=actor, campus_id=campus.id, name="Jane", username="jane", password=PASSWORD
    )

    with pytest.raises(OwnerNotFound):
        service.disable_owner(actor=actor, user_id=admin.id)

    with pytest.raises(OwnerNotFound):
        service.disable_owner(actor=actor, user_id=999)


# ---------------------------------------------------------------------------
# Per-Campus KPI cards
# ---------------------------------------------------------------------------


def _seed_money(db, school_id, campus_id, *, amount, paid):
    """One campus with a billed student and an optional payment for this month."""
    today = date.today()
    campus_scope = RequestScope(user=None, school_id=school_id, campus_id=campus_id)
    with scope_context(campus_scope):
        with db.session() as session:
            student = make_billed_student(
                session,
                enrolled_on=date(today.year, today.month, 1),
                amount=amount,
                class_name=f"Class {campus_id}",
            )
            if paid:
                add_payment(session, student.id, paid, today.month, today.year)
            session.commit()


def test_campus_kpi_cards_reflect_each_campus_only(service, actor, db):
    with db.session() as session:
        school = session.query(School).one()
        campus_b = Campus(school_id=school.id, name="Campus B")
        session.add(campus_b)
        session.commit()
        campus_b_id = campus_b.id
        campus_a_id = session.query(Campus).filter_by(name="Campus A").one().id

    _seed_money(db, school.id, campus_a_id, amount=10000, paid=5000)
    _seed_money(db, school.id, campus_b_id, amount=10000, paid=0)

    reports = ReportService(db, arrears=ArrearsService(db))
    svc = SchoolDashboardService(db, audit=AuditService(db), reports=reports)

    with scope_context(RequestScope(user=None, school_id=school.id, campus_id=None)):
        summaries = svc.list_campuses()

    by_name = {s.campus.name: s.kpi for s in summaries}
    assert by_name["Campus A"].collected_cents == 5000
    assert by_name["Campus A"].paid_cents == 5000
    assert by_name["Campus A"].expected_cents == 10000
    assert by_name["Campus A"].arrears_cents == 5000
    assert by_name["Campus A"].collected_percent == 50
    assert by_name["Campus B"].collected_cents == 0
    assert by_name["Campus B"].paid_cents == 0
    assert by_name["Campus B"].expected_cents == 10000
    assert by_name["Campus B"].arrears_cents == 10000
    assert by_name["Campus B"].collected_percent == 0


def test_kpis_are_none_without_a_report_service(service, actor):
    service.create_campus(actor=actor, name="Branch")

    summaries = service.list_campuses()

    assert summaries and all(summary.kpi is None for summary in summaries)

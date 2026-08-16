"""Audit campus scoping (multi-school 06).

Service-level tests with a seeded scope, following tickets 03/04's pattern: an
entry is stamped with the acting scope's Campus at write time (NULL for
school-level and system actions), and browsing — list, count, action dropdown —
only ever returns what the acting scope may see. Two Campuses of one School, an
Admin bound to each, and a bound Superadmin; legacy NULL-campus rows stay
visible to every scope. Route concerns live in ``test_audit_routes.py``.
"""

import pytest

from app.audit.service import AuditActions, AuditService
from app.models import AuditLogEntry
from app.tenants.scope import RequestScope, scope_context
from tests.test_tenant_scope import seed_tenant_world


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


def log_entries(audit, *, user, action, summary):
    with scope_context(RequestScope.for_user(user)):
        audit.log(user=user, action=action, summary=summary)


# ---------------------------------------------------------------------------
# Write side: entries are stamped with the acting scope's Campus
# ---------------------------------------------------------------------------


def test_a_campus_bound_entry_is_stamped_with_the_acting_campus(audit, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        audit.log(
            user=admin_a, action=AuditActions.CLASS_CREATE, summary="Created class X"
        )

    (entry,) = session.query(AuditLogEntry).all()
    assert entry.campus_id == campus_a.id


def test_a_school_bound_entry_is_stamped_null(audit, session):
    _school, _campus_a, _campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(superadmin)):
        audit.log(
            user=superadmin,
            action=AuditActions.USER_CREATE,
            summary="Created an owner account",
        )

    (entry,) = session.query(AuditLogEntry).all()
    assert entry.campus_id is None


def test_a_system_entry_outside_a_scope_is_stamped_null(audit, session):
    _school, _campus_a, _campus_b, _admin_a, _admin_b, _sa = seed_tenant_world(session)

    audit.log(user=None, action=AuditActions.SETUP, summary="Created the first Admin")

    (entry,) = session.query(AuditLogEntry).all()
    assert entry.campus_id is None


# ---------------------------------------------------------------------------
# Browse side: list_entries / count / list_actions respect the scope
# ---------------------------------------------------------------------------


def seed_entries(audit, session):
    """One campus-scoped entry per campus plus one NULL system entry."""
    school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    log_entries(audit, user=admin_a, action=AuditActions.LOGIN, summary="Admin A logged in")
    log_entries(audit, user=admin_b, action=AuditActions.LOGIN, summary="Admin B logged in")
    log_entries(audit, user=None, action=AuditActions.SETUP, summary="Setup ran")
    return school, campus_a, campus_b, admin_a, admin_b, superadmin


def test_campus_admin_browses_only_own_campus_and_null_entries(audit, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_entries(audit, session)

    with scope_context(RequestScope.for_user(admin_a)):
        entries = audit.list_entries(limit=50)
        seen_campuses = {entry.campus_id for entry in entries}
        assert seen_campuses == {campus_a.id, None}
        assert campus_b.id not in seen_campuses
        assert audit.count() == 2
        assert "setup" in audit.list_actions()
        assert "login" in audit.list_actions()


def test_campus_admin_never_sees_another_campus_entries(audit, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_entries(audit, session)

    with scope_context(RequestScope.for_user(admin_a)):
        entries = audit.list_entries(limit=50)

    summaries = {entry.summary for entry in entries}
    assert "Admin A logged in" in summaries
    assert "Admin B logged in" not in summaries
    assert all(entry.campus_id in (campus_a.id, None) for entry in entries)


def test_superadmin_browses_every_campus_plus_school_level_entries(audit, session):
    _school, campus_a, campus_b, _admin_a, _admin_b, superadmin = seed_entries(audit, session)

    with scope_context(RequestScope.for_user(superadmin)):
        entries = audit.list_entries(limit=50)
        assert {entry.campus_id for entry in entries} == {campus_a.id, campus_b.id, None}
        assert audit.count() == 3


def test_browse_filters_by_action_within_the_scope(audit, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_entries(audit, session)

    with scope_context(RequestScope.for_user(admin_a)):
        logins = audit.list_entries(action=AuditActions.LOGIN)

    assert {entry.campus_id for entry in logins} == {campus_a.id}
    assert {entry.summary for entry in logins} == {"Admin A logged in"}

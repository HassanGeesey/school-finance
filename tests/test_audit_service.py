"""Audit service: append-only entries, browsing (recent-first, filtered), and
the auth wiring that records setup/login/logout.

Business rules only — the single testing seam. Route concerns live in
``test_audit_routes.py``.
"""

from datetime import datetime, timezone

import pytest

from app.audit.service import AuditActions, AuditError, AuditService
from app.auth.service import AuthService
from app.models import AuditLogEntry, User, UserRoles, utcnow
from app.profile.service import ProfileService

PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def authed(db) -> AuthService:
    """AuthService wired to a real AuditService so auth actions log entries."""
    return AuthService(db, audit=AuditService(db), profile=ProfileService(db))


def test_log_creates_an_entry_with_no_user(audit, session):
    entry = audit.log(user=None, action="setup", summary="Created the first Admin account")

    assert entry.id is not None
    row = session.query(AuditLogEntry).one()
    assert row.action == "setup"
    assert row.summary == "Created the first Admin account"
    assert row.user_id is None


def test_log_records_the_acting_user(audit, session):
    user = User(username="alice", name="Alice", password_hash="x", role=UserRoles.ADMIN)
    session.add(user)
    session.commit()

    audit.log(user=user, action="login", summary="Alice logged in")

    row = session.query(AuditLogEntry).one()
    assert row.user_id == user.id
    assert row.user.name == "Alice"


def test_log_stamps_each_entry_with_a_timestamp(audit):
    before = datetime.now(timezone.utc).replace(tzinfo=None)

    entry = audit.log(user=None, action="login", summary="A logged in")

    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert before <= entry.created_at <= after


def test_log_requires_an_action(audit):
    with pytest.raises(AuditError):
        audit.log(user=None, action="", summary="something happened")
    with pytest.raises(AuditError):
        audit.log(user=None, action="   ", summary="something happened")


def test_log_requires_a_summary(audit):
    with pytest.raises(AuditError):
        audit.log(user=None, action="login", summary="")


def test_list_entries_returns_most_recent_first(audit):
    audit.log(user=None, action="setup", summary="first")
    audit.log(user=None, action="login", summary="second")
    audit.log(user=None, action="logout", summary="third")

    entries = audit.list_entries()
    assert [e.summary for e in entries] == ["third", "second", "first"]


def test_list_entries_filters_by_action(audit):
    audit.log(user=None, action="setup", summary="setup summary")
    audit.log(user=None, action="login", summary="login one")
    audit.log(user=None, action="login", summary="login two")

    entries = audit.list_entries(action="login")
    assert [e.summary for e in entries] == ["login two", "login one"]


def test_list_entries_paginates(audit):
    for index in range(5):
        audit.log(user=None, action="login", summary=f"entry {index}")

    page_one = audit.list_entries(limit=2, offset=0)
    page_two = audit.list_entries(limit=2, offset=2)

    assert [e.summary for e in page_one] == ["entry 4", "entry 3"]
    assert [e.summary for e in page_two] == ["entry 2", "entry 1"]


def test_count_respects_the_action_filter(audit):
    audit.log(user=None, action="setup", summary="s")
    audit.log(user=None, action="login", summary="l")

    assert audit.count() == 2
    assert audit.count(action="login") == 1
    assert audit.count(action="logout") == 0


def test_list_actions_returns_each_distinct_action_once(audit):
    audit.log(user=None, action="setup", summary="s")
    audit.log(user=None, action="login", summary="l")
    audit.log(user=None, action="login", summary="l2")

    assert audit.list_actions() == ["login", "setup"]


def test_setup_first_admin_writes_a_system_audit_entry(authed, session):
    authed.setup_first_admin(name="Head Teacher", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    row = session.query(AuditLogEntry).one()
    assert row.action == AuditActions.SETUP
    assert row.user_id is None
    assert "Head Teacher" in row.summary
    assert "admin" in row.summary


def test_login_writes_a_login_audit_entry(authed, session):
    authed.setup_first_admin(name="Head Teacher", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    user, _token = authed.login("admin", PASSWORD)

    row = session.query(AuditLogEntry).filter_by(action=AuditActions.LOGIN).one()
    assert row.user_id == user.id
    assert "Head Teacher" in row.summary


def test_login_failure_writes_no_audit_entry(authed, session):
    authed.setup_first_admin(name="Head Teacher", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    assert authed.login("admin", "wrong password") is None
    assert session.query(AuditLogEntry).filter_by(action=AuditActions.LOGIN).count() == 0


def test_logout_writes_a_logout_audit_entry(authed, session):
    authed.setup_first_admin(name="Head Teacher", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    user, token = authed.login("admin", PASSWORD)

    authed.destroy_session(token)

    row = session.query(AuditLogEntry).filter_by(action=AuditActions.LOGOUT).one()
    assert row.user_id == user.id
    assert "Head Teacher" in row.summary

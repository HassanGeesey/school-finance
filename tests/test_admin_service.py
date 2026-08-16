"""Admin user-management service: create/disable/enable users, reset passwords.

Business rules only — the single testing seam. Route concerns live in
``test_admin_routes.py``. Finance officers are blocked at the route layer; this
service assumes the actor is an Admin and concentrates on the user lifecycle.
"""

import pytest

from app.admin.service import (
    AdminUserError,
    AdminUserService,
    CannotDisableSelf,
    LastActiveAdmin,
    UserNotFound,
    UsernameTaken,
)
from app.audit.service import AuditActions, AuditService
from app.auth.service import AuthService, verify_password
from app.models import AuditLogEntry, Campus, School, User, UserRoles
from app.profile.service import ProfileService
from app.tenants.scope import RequestScope, require_scope, scope_context

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def school_world(db):
    """A School-scoped context: the classic admin lifecycle (create Admins,
    self-disable protection, last-admin protection) happens at the School level.
    """
    with db.session() as session:
        school = School(name="School")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="Campus")
        session.add(campus)
        session.commit()
        scope_ = RequestScope(user=None, school_id=school.id, campus_id=None)
    with scope_context(scope_):
        yield scope_


@pytest.fixture(autouse=True)
def _scoped(school_world):
    return school_world


@pytest.fixture()
def admin(db) -> AdminUserService:
    return AdminUserService(db, audit=AuditService(db))


@pytest.fixture()
def auth(db) -> AuthService:
    return AuthService(db, audit=AuditService(db), profile=ProfileService(db))


def _actor(session, *, name="Head Teacher", username="admin", role=UserRoles.ADMIN) -> User:
    sc = require_scope()
    user = User(
        name=name,
        username=username,
        password_hash="x",
        role=role,
        school_id=sc.school_id,
        campus_id=sc.campus_id,
    )
    session.add(user)
    session.commit()
    return user


def audit_actions(session, action: str) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=action)
        .order_by(AuditLogEntry.id)
        .all()
    )


def test_create_user_makes_an_active_account_with_the_expected_role(admin, session):
    created = admin.create_user(
        actor=None,
        name="Cashier",
        username="cashier",
        password=PASSWORD,
        role=UserRoles.FINANCE,
    )

    assert created.id is not None
    assert created.role == UserRoles.FINANCE
    assert created.is_active is True
    stored = session.query(User).filter_by(username="cashier").one()
    assert verify_password(PASSWORD, stored.password_hash)


def test_create_user_can_make_an_admin(admin, session):
    created = admin.create_user(
        actor=None,
        name="Deputy",
        username="deputy",
        password=PASSWORD,
        role=UserRoles.ADMIN,
    )

    assert created.role == UserRoles.ADMIN


def test_a_campus_bound_admin_cannot_create_an_admin(db, admin, session):
    # A Campus-scoped Admin manages only Finance officers (ticket 08): creating
    # or promoting an Admin is the Superadmin's School-level job.
    with db.session() as session:
        school = School(name="School")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="Campus A")
        session.add(campus)
        session.commit()
        scope_ = RequestScope(user=None, school_id=school.id, campus_id=campus.id)
    with scope_context(scope_):
        with pytest.raises(AdminUserError):
            admin.create_user(
                actor=None, name="Deputy", username="deputy", password=PASSWORD, role=UserRoles.ADMIN
            )
        created = admin.create_user(
            actor=None, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
        )
        assert created.role == UserRoles.FINANCE
        assert created.campus_id == campus.id
        assert created.school_id == school.id


def test_create_user_requires_name_username_and_password(admin):
    with pytest.raises(AdminUserError):
        admin.create_user(actor=None, name="", username="u", password=PASSWORD, role=UserRoles.FINANCE)
    with pytest.raises(AdminUserError):
        admin.create_user(actor=None, name="N", username="", password=PASSWORD, role=UserRoles.FINANCE)
    with pytest.raises(AdminUserError):
        admin.create_user(actor=None, name="N", username="u", password="", role=UserRoles.FINANCE)


def test_create_user_rejects_an_unknown_role(admin):
    with pytest.raises(AdminUserError):
        admin.create_user(actor=None, name="N", username="u", password=PASSWORD, role="superuser")


def test_create_user_rejects_a_duplicate_username_case_insensitively(admin, session):
    admin.create_user(
        actor=None, name="First", username="Cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    with pytest.raises(UsernameTaken):
        admin.create_user(
            actor=None, name="Second", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
        )

    assert session.query(User).count() == 1


def test_create_user_is_audited(admin, session):
    admin.create_user(
        actor=None, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    (entry,) = audit_actions(session, AuditActions.USER_CREATE)
    assert "cashier" in entry.summary
    assert "Cashier" in entry.summary


def test_disable_user_marks_the_account_inactive(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    admin.disable_user(actor=actor, user_id=target.id)

    assert session.query(User).filter_by(id=target.id).one().is_active is False


def test_disabled_user_cannot_log_in(admin, auth, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=target.id)

    assert auth.authenticate("cashier", PASSWORD) is None


def test_admin_cannot_disable_their_own_account(admin, session):
    actor = _actor(session)

    with pytest.raises(CannotDisableSelf):
        admin.disable_user(actor=actor, user_id=actor.id)

    assert actor.is_active is True


def test_the_last_active_admin_cannot_be_disabled(admin, session):
    actor = _actor(session)

    with pytest.raises(LastActiveAdmin):
        admin.disable_user(actor=None, user_id=actor.id)


def test_disabling_an_admin_is_allowed_while_another_active_admin_remains(admin, session):
    actor = _actor(session)
    deputy = admin.create_user(
        actor=actor, name="Deputy", username="deputy", password=PASSWORD, role=UserRoles.ADMIN
    )
    disabled = admin.create_user(
        actor=actor, name="Old admin", username="oldadmin", password=PASSWORD, role=UserRoles.ADMIN
    )

    admin.disable_user(actor=actor, user_id=disabled.id)

    assert session.query(User).filter_by(id=actor.id).one().is_active is True
    assert session.query(User).filter_by(id=deputy.id).one().is_active is True
    assert session.query(User).filter_by(id=disabled.id).one().is_active is False


def test_disable_user_unknown_id_raises(admin, session):
    actor = _actor(session)

    with pytest.raises(UserNotFound):
        admin.disable_user(actor=actor, user_id=999)


def test_disable_user_is_audited(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    admin.disable_user(actor=actor, user_id=target.id)

    (entry,) = audit_actions(session, AuditActions.USER_DISABLE)
    assert "cashier" in entry.summary


def test_enable_user_reactivates_an_inactive_account(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=target.id)

    admin.enable_user(actor=actor, user_id=target.id)

    assert session.query(User).filter_by(id=target.id).one().is_active is True


def test_enabled_user_can_log_in_again(admin, auth, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=target.id)
    admin.enable_user(actor=actor, user_id=target.id)

    assert auth.authenticate("cashier", PASSWORD) is not None


def test_enable_user_is_audited(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=target.id)

    admin.enable_user(actor=actor, user_id=target.id)

    assert len(audit_actions(session, AuditActions.USER_ENABLE)) == 1


def test_enabling_an_already_active_user_is_a_noop_without_audit(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    admin.enable_user(actor=actor, user_id=target.id)

    assert audit_actions(session, AuditActions.USER_ENABLE) == []


def test_reset_password_replaces_the_hash(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    admin.reset_password(actor=actor, user_id=target.id, password="brand new passphrase")

    stored = session.query(User).filter_by(id=target.id).one()
    assert verify_password("brand new passphrase", stored.password_hash)
    assert not verify_password(PASSWORD, stored.password_hash)


def test_reset_password_requires_a_new_password(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    with pytest.raises(AdminUserError):
        admin.reset_password(actor=actor, user_id=target.id, password="   ")

    stored = session.query(User).filter_by(id=target.id).one()
    assert verify_password(PASSWORD, stored.password_hash)


def test_reset_password_is_audited(admin, session):
    actor = _actor(session)
    target = admin.create_user(
        actor=actor, name="Cashier", username="cashier", password=PASSWORD, role=UserRoles.FINANCE
    )

    admin.reset_password(actor=actor, user_id=target.id, password="brand new passphrase")

    (entry,) = audit_actions(session, AuditActions.USER_PASSWORD_RESET)
    assert "cashier" in entry.summary


def test_list_users_orders_active_first_then_by_name(admin, session):
    actor = _actor(session, name="Boss", username="boss")
    zoe = admin.create_user(
        actor=actor, name="Zoe", username="zoe", password=PASSWORD, role=UserRoles.FINANCE
    )
    ann = admin.create_user(
        actor=actor, name="Ann", username="ann", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=ann.id)

    users = admin.list_users()
    names = [user.username for user in users]

    assert names == ["boss", "zoe", "ann"]  # active first, then by name; disabled last


def test_list_users_puts_disabled_users_last(admin, session):
    actor = _actor(session, name="Boss", username="boss")
    zoe = admin.create_user(
        actor=actor, name="Zoe", username="zoe", password=PASSWORD, role=UserRoles.FINANCE
    )
    admin.disable_user(actor=actor, user_id=zoe.id)

    users = admin.list_users()

    assert [u.username for u in users] == ["boss", "zoe"]

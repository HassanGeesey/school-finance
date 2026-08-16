"""Admin user-management service layer.

Business rules for the staff account lifecycle: creating users (Admin or
Finance officer), disabling and re-enabling accounts, and resetting passwords.
Routes are thin adapters over this module — it is the single testing seam.

Rules that live here:
- Only the Admin role reaches these methods (enforced at the route layer);
  this service concentrates on the user lifecycle itself.
- A username is required and unique across users, case-insensitively.
- The role is one of ``admin`` / ``finance``.
- A password is required for new accounts and for resets (hashed with PBKDF2
  via ``app.auth.service``).
- There are no hard deletes: disabling an account is a status transition.
  A disabled account can no longer log in (``AuthService`` checks ``is_active``)
  but its history — payments recorded, audit entries — stays intact.
- An admin cannot disable their own account.
- The last active admin cannot be disabled, so the app can never be locked out.
- Re-enabling an already-active account is a no-op (no audit entry).
- Every lifecycle change writes one audit entry; a rejected change writes none.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..auth.service import hash_password
from ..db import Database
from ..models import User, UserRoles
from ..tenants.scope import RequestScope, require_scope

USER_ROLE_LABELS = {
    UserRoles.ADMIN: "Admin",
    UserRoles.FINANCE: "Finance officer",
}
SCHOOL_ROLE_LABELS = {
    UserRoles.SUPERADMIN: "Superadmin",
    UserRoles.OWNER: "Owner",
}
ALL_ROLE_LABELS = {**USER_ROLE_LABELS, **SCHOOL_ROLE_LABELS}
VALID_ROLES = set(USER_ROLE_LABELS)


class AdminUserError(Exception):
    """Rejected input or state in a user-management operation."""


class UserNotFound(AdminUserError):
    """No user exists with the given id."""


class UsernameTaken(AdminUserError):
    """A user with that username already exists."""


class CannotDisableSelf(AdminUserError):
    """An admin cannot disable their own account."""


class LastActiveAdmin(AdminUserError):
    """Disabling this account would leave no active Admin."""


class AdminUserService:
    """Admin business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _users_in_scope(session: Session, scope_: RequestScope):
        """The user query narrowed to the acting scope: its Campus for a
        Campus-bound scope, its School for a School-bound scope."""
        if scope_.campus_id is not None:
            return session.query(User).filter(User.campus_id == scope_.campus_id)
        return session.query(User).filter(User.school_id == scope_.school_id)

    def _get_user(self, session: Session, user_id: int) -> User:
        scope_ = require_scope()
        user = self._users_in_scope(session, scope_).filter(User.id == user_id).one_or_none()
        if user is None:
            raise UserNotFound(f"No user with id {user_id} exists.")
        return user

    @staticmethod
    def _username_taken(session: Session, username: str, exclude_id: int | None = None) -> bool:
        query = session.query(User.id).filter(func.lower(User.username) == username.lower())
        if exclude_id is not None:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    def _active_admin_count(self, session: Session) -> int:
        scope_ = require_scope()
        return (
            self._users_in_scope(session, scope_)
            .filter(User.role == UserRoles.ADMIN, User.is_active.is_(True))
            .count()
        )

    @staticmethod
    def _assert_manageable(user: User) -> None:
        """A Campus-bound Admin manages only Finance officers of their own Campus
        (multi-school ticket 08). ``_get_user`` already narrowed the target to the
        acting scope; this adds the Finance-only rule so a Campus Admin can never
        disable/enable or reset the password of another Admin."""
        scope_ = require_scope()
        if scope_.campus_id is not None and user.role != UserRoles.FINANCE:
            raise AdminUserError(
                "Campus admins can only manage Finance officer accounts."
            )

    # -- Reads ---------------------------------------------------------------

    def list_users(self) -> list[User]:
        """The acting scope's users: active first, then by username."""
        scope_ = require_scope()
        with self._session() as session:
            return (
                self._users_in_scope(session, scope_)
                .order_by(User.is_active.desc(), func.lower(User.username), User.id)
                .all()
            )

    # -- User lifecycle ------------------------------------------------------

    def create_user(
        self,
        *,
        actor: User | None,
        name: str,
        username: str,
        password: str,
        role: str,
    ) -> User:
        """Create a new staff account. ``actor`` is who performed the action."""
        name = (name or "").strip()
        username = (username or "").strip()
        if not name or not username:
            raise AdminUserError("Name and username are required.")
        if not password:
            raise AdminUserError("A password is required.")
        if role not in VALID_ROLES:
            raise AdminUserError("Choose Admin or Finance officer.")
        scope_ = require_scope()
        # A Campus-bound Admin manages only their own Campus's Finance officers
        # (multi-school ticket 08): they can never create or promote other
        # Admins — that is the Superadmin's School-level job.
        if scope_.campus_id is not None and role != UserRoles.FINANCE:
            raise AdminUserError(
                "Campus admins can only create Finance officer accounts."
            )

        with self._session() as session:
            if self._username_taken(session, username):
                raise UsernameTaken(
                    f"A user with the username '{username}' already exists."
                )
            user = User(
                name=name,
                username=username,
                password_hash=hash_password(password),
                role=role,
                # Tenant scope: the new account belongs to the acting scope —
                # its Campus (Admin/Finance) or its School (Superadmin/Owner).
                school_id=scope_.school_id,
                campus_id=scope_.campus_id,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        self._log(
            user=actor,
            action=AuditActions.USER_CREATE,
            summary=(
                f"Created {USER_ROLE_LABELS[role]} account {user.username} "
                f"({user.name})"
            ),
        )
        return user

    def disable_user(self, *, actor: User | None, user_id: int) -> User:
        """Disable an account. Refuses self-disable and lockout of the last Admin."""
        with self._session() as session:
            user = self._get_user(session, user_id)
            if actor is not None and user.id == actor.id:
                raise CannotDisableSelf("You cannot disable your own account.")
            self._assert_manageable(user)
            if (
                user.role == UserRoles.ADMIN
                and user.is_active
                and self._active_admin_count(session) <= 1
            ):
                raise LastActiveAdmin(
                    "This is the only active Admin account. Create another "
                    "Admin before disabling it."
                )
            user.is_active = False
            session.commit()
            session.refresh(user)
        self._log(
            user=actor,
            action=AuditActions.USER_DISABLE,
            summary=f"Disabled user {user.username} ({user.name})",
        )
        return user

    def enable_user(self, *, actor: User | None, user_id: int) -> User:
        """Re-enable a disabled account. No-op (and unaudited) if already active."""
        with self._session() as session:
            user = self._get_user(session, user_id)
            self._assert_manageable(user)
            if user.is_active:
                return user
            user.is_active = True
            session.commit()
            session.refresh(user)
        self._log(
            user=actor,
            action=AuditActions.USER_ENABLE,
            summary=f"Enabled user {user.username} ({user.name})",
        )
        return user

    def reset_password(self, *, actor: User | None, user_id: int, password: str) -> User:
        """Replace a user's password hash. A password is required."""
        if not (password or "").strip():
            raise AdminUserError("A new password is required.")
        with self._session() as session:
            user = self._get_user(session, user_id)
            self._assert_manageable(user)
            user.password_hash = hash_password(password)
            session.commit()
            session.refresh(user)
        self._log(
            user=actor,
            action=AuditActions.USER_PASSWORD_RESET,
            summary=f"Reset password for user {user.username} ({user.name})",
        )
        return user

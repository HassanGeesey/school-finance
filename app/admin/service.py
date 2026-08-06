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

USER_ROLE_LABELS = {
    UserRoles.ADMIN: "Admin",
    UserRoles.FINANCE: "Finance officer",
}
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
    def _get_user(session: Session, user_id: int) -> User:
        user = session.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise UserNotFound(f"No user with id {user_id} exists.")
        return user

    @staticmethod
    def _username_taken(session: Session, username: str, exclude_id: int | None = None) -> bool:
        query = session.query(User.id).filter(func.lower(User.username) == username.lower())
        if exclude_id is not None:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _active_admin_count(session: Session) -> int:
        return (
            session.query(User)
            .filter(User.role == UserRoles.ADMIN, User.is_active.is_(True))
            .count()
        )

    # -- Reads ---------------------------------------------------------------

    def list_users(self) -> list[User]:
        """All users: active first, then by username."""
        with self._session() as session:
            return (
                session.query(User)
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
            user.password_hash = hash_password(password)
            session.commit()
            session.refresh(user)
        self._log(
            user=actor,
            action=AuditActions.USER_PASSWORD_RESET,
            summary=f"Reset password for user {user.username} ({user.name})",
        )
        return user

"""Auth service layer: password hashing, first-admin setup, server-side sessions.

Business rules live here; routes are thin adapters (see ``app/auth/routes.py``).
This module is the seam the auth tests target with an in-memory database.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..config import settings
from ..db import Database
from ..models import AuthSession, School, User, UserRoles, utcnow
from ..profile.service import ProfileService
from ..tenants.service import ensure_bootstrap_on


class AuthError(Exception):
    """Rejected input or state while creating an account."""


class SetupNotAvailable(AuthError):
    """The first admin already exists, so the setup wizard must not run."""


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a per-user random salt.

    Format: ``pbkdf2_sha256$<iterations>$<salt hex>$<digest hex>``.
    """
    iterations = settings.PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected_hex)


def safe_post_login_target(next_path: str) -> str:
    """Only local paths are acceptable post-login targets (no open redirects)."""
    if next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def session_max_age_seconds() -> int:
    """Lifetime of a session, used both for the DB row and the cookie."""
    return settings.SESSION_TTL_DAYS * 24 * 60 * 60


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Auth business rules. Each method is one unit of work on its own session."""

    def __init__(
        self,
        db: Database,
        *,
        audit: AuditService | None = None,
        profile: ProfileService,
    ) -> None:
        self._db = db
        self._audit = audit
        self._profile = profile

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    def has_users(self) -> bool:
        with self._session() as session:
            return self._has_users(session)

    @staticmethod
    def _has_users(session: Session) -> bool:
        return session.query(User).count() > 0

    @staticmethod
    def _validate_setup_inputs(
        *, name: str, username: str, password: str, school_name: str
    ) -> tuple[str, str, str, str]:
        """Strip the wizard's fields and enforce the first-run requirements.

        Shared by the offline and cloud setup paths so their validation cannot
        drift apart. Returns the cleaned values; the password is not stripped —
        an empty password is the only one rejected.
        """
        name = (name or "").strip()
        username = (username or "").strip()
        school_name = (school_name or "").strip()
        if not name or not username:
            raise AuthError("Name and username are required.")
        if not password:
            raise AuthError("A password is required.")
        if not school_name:
            raise AuthError("A school name is required.")
        return name, username, password, school_name

    def setup_first_admin(
        self, *, name: str, username: str, password: str, school_name: str = ""
    ) -> User:
        """Create the first Admin account and name the implicit Campus.

        The Admin is bound to the implicit School + Campus (multi-school ticket
        01): ``ensure_bootstrap_on`` creates exactly one of each in the same
        session, and the Admin is stamped with their ids before the commit. The
        school name is required here: the wizard is the first time the school's
        identity is captured, so it is recorded on the implicit Campus via the
        profile service (per-Campus branding, ticket 07). Raises when users
        already exist.
        """
        name, username, password, school_name = self._validate_setup_inputs(
            name=name, username=username, password=password, school_name=school_name
        )

        with self._session() as session:
            if self._has_users(session):
                raise SetupNotAvailable("An admin account already exists.")
            school, campus = ensure_bootstrap_on(session)
            user = User(
                name=name,
                username=username,
                password_hash=hash_password(password),
                role=UserRoles.ADMIN,
                school_id=school.id,
                campus_id=campus.id,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        self._profile.update_profile(user=user, campus=campus, school_name=school_name)
        self._log(
            user=None,
            action=AuditActions.SETUP,
            summary=(
                f"Created the first Admin account: {name} ({username}); "
                f"school profile set up as {school_name}"
            ),
        )
        return user

    def setup_school_superadmin(
        self, *, name: str, username: str, password: str, school_name: str = ""
    ) -> User:
        """Create the School and its Superadmin account (cloud path, UR-17).

        First-run provisioning on the cloud path: the wizard names the School
        and creates its owner at the top in one step. No Campus is created here
        — the Superadmin creates campuses later from the School Dashboard
        (ticket 05), and the School's own ``name`` row carries the school's
        identity until then. Raises when users already exist.
        """
        name, username, password, school_name = self._validate_setup_inputs(
            name=name, username=username, password=password, school_name=school_name
        )

        with self._session() as session:
            if self._has_users(session):
                raise SetupNotAvailable("An admin account already exists.")
            school = School(name=school_name)
            session.add(school)
            session.flush()
            user = User(
                name=name,
                username=username,
                password_hash=hash_password(password),
                role=UserRoles.SUPERADMIN,
                school_id=school.id,
                campus_id=None,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        self._log(
            user=None,
            action=AuditActions.SETUP,
            summary=(
                f"Created the first Superadmin account: {name} ({username}); "
                f"school set up as {school_name}"
            ),
        )
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user when credentials are valid and the account is active."""
        with self._session() as session:
            user = session.query(User).filter(
                func.lower(User.username) == username.lower()
            ).first()
            if user is None:
                return None
            if not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return user

    def create_session(self, user: User) -> str:
        """Create a session row and return the raw token that goes in the cookie."""
        token = secrets.token_urlsafe(32)
        with self._session() as session:
            session.add(
                AuthSession(
                    user_id=user.id,
                    token_hash=_token_digest(token),
                    expires_at=utcnow() + timedelta(days=settings.SESSION_TTL_DAYS),                )
            )
            session.commit()
        return token

    def login(self, username: str, password: str) -> tuple[User, str] | None:
        """Authenticate and create a session, then record the login in the audit log."""
        user = self.authenticate(username, password)
        if user is None:
            return None
        token = self.create_session(user)
        self._log(user=user, action=AuditActions.LOGIN, summary=f"{user.name} logged in")
        return user, token

    def user_for_token(self, token: str | None) -> User | None:
        """Resolve a session token to its user, rejecting expired/invalid ones."""
        if not token:
            return None
        with self._session() as session:
            row = (
                session.query(AuthSession)
                .filter(AuthSession.token_hash == _token_digest(token))
                .first()
            )
            if row is None:
                return None
            if row.expires_at < utcnow():
                session.delete(row)
                session.commit()
                return None
            user = session.query(User).filter(User.id == row.user_id).first()
            if user is None or not user.is_active:
                session.delete(row)
                session.commit()
                return None
            return user

    def destroy_session(self, token: str | None) -> None:
        """Log out: remove the session row so the token stops resolving.

        Attribution is read from the session row itself, so a destroyed session
        is always logged — the caller cannot silently drop the entry.
        """
        if not token:
            return
        with self._session() as session:
            row = (
                session.query(AuthSession)
                .filter(AuthSession.token_hash == _token_digest(token))
                .first()
            )
            if row is None:
                return
            user = session.query(User).filter(User.id == row.user_id).first()
            session.delete(row)
            session.commit()
        if user is not None:
            self._log(user=user, action=AuditActions.LOGOUT, summary=f"{user.name} logged out")

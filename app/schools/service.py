"""School Dashboard service layer (multi-school ticket 08).

The Superadmin's working surface and the Owner/Shareholder's read-only view.
This service owns the School-level facts the Campus-scoped services never see:
the School's Campuses (create/archive), the per-Campus KPI cards, and the
Owner accounts (create/revoke). Routes are thin adapters over this module — it
is the single testing seam.

Rules that live here:
- Only School-bound roles reach these methods (enforced at the route layer);
  every method resolves the School from the acting scope's ``school_id``.
- A Campus needs a name; the rest of the identity fields (address, phone,
  email, website) are optional and left for the Campus Admin to edit.
- A Campus is created optionally with its first Campus Admin: the admin's
  name/username/password are all-or-none, and the username must be unique
  across users. The admin is bound to the new Campus (role ``admin``).
- Archiving a Campus is a soft delete: the row and its history stay, the
  ``archived`` flag flips. The last active Campus of the School cannot be
  archived (mirrors the last-active-admin protection in ``AdminUserService``),
  so a School can never be left without a branch.
- Owner accounts belong to the School (``role=owner``, ``school_id`` set) and
  are strictly read-only; creating one requires a username unique across users.
- Every lifecycle change writes one audit entry (school-level, NULL Campus per
  MD-2); a rejected change writes none.
- Per-Campus KPI cards (collections, expenses, arrears, expected-vs-paid,
  active students) render from each Campus's own data: the report service is
  run under a Campus-scoped context so a two-Campus School is compared side by
  side, each card showing only its own branch's figures. When no report service
  was injected (test mini-app), KPIs come back ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..auth.service import hash_password
from ..db import Database
from ..models import Campus, School, User, UserRoles
from ..tenants.scope import RequestScope, require_scope, scope_context


class SchoolError(Exception):
    """Rejected input or state in a School-level operation."""


class SchoolNotFound(SchoolError):
    """No School exists for the acting scope."""


class CampusNotFound(SchoolError):
    """No Campus with the given id exists in the School."""


class OwnerNotFound(SchoolError):
    """No Owner account with the given id exists in the School."""


class UsernameTaken(SchoolError):
    """A user with that username already exists."""


class LastActiveCampus(SchoolError):
    """Archiving this Campus would leave the School without an active branch."""


@dataclass(frozen=True)
class CampusKpi:
    """One Campus's current-month KPIs for the School Dashboard cards."""

    collected_cents: int
    expenses_cents: int
    arrears_cents: int
    expected_cents: int
    paid_cents: int
    active_student_count: int

    @property
    def collected_percent(self) -> int:
        """Expected-vs-paid as a percentage (0 when nothing was expected)."""
        if self.expected_cents <= 0:
            return 0
        return round(min(self.paid_cents / self.expected_cents, 1.0) * 100)


@dataclass(frozen=True)
class CampusSummary:
    """One Campus card on the School Dashboard."""

    campus: Campus
    admin: User | None
    kpi: CampusKpi | None


class SchoolDashboardService:
    """School business rules. Each method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None, reports=None) -> None:
        self._db = db
        self._audit = audit
        self._reports = reports

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    def _school_id(self) -> int:
        cur = require_scope()
        if cur.school_id is None:
            raise SchoolNotFound("This area needs a School scope.")
        return cur.school_id

    @staticmethod
    def _username_taken(session: Session, username: str, exclude_id: int | None = None) -> bool:
        query = session.query(User.id).filter(func.lower(User.username) == username.lower())
        if exclude_id is not None:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    def _get_school(self, session: Session) -> School:
        school = session.get(School, self._school_id())
        if school is None:
            raise SchoolNotFound("No School exists for the acting scope.")
        return school

    def _get_campus(self, session: Session, campus_id: int) -> Campus:
        school = self._get_school(session)
        campus = (
            session.query(Campus)
            .filter(Campus.id == campus_id, Campus.school_id == school.id)
            .one_or_none()
        )
        if campus is None:
            raise CampusNotFound(f"No Campus with id {campus_id} exists in this School.")
        return campus

    def _active_campus_count(self, session: Session) -> int:
        return (
            session.query(Campus)
            .filter(Campus.school_id == self._school_id(), Campus.archived.is_(False))
            .count()
        )

    # -- Reads ---------------------------------------------------------------

    def school(self) -> School:
        """The acting School (for the dashboard header)."""
        with self._session() as session:
            return self._get_school(session)

    def list_campuses(self) -> list[CampusSummary]:
        """The School's Campuses, active first then by name, each with its KPIs."""
        with self._session() as session:
            school = self._get_school(session)
            campuses = (
                session.query(Campus)
                .filter(Campus.school_id == school.id)
                .order_by(Campus.archived.asc(), func.lower(Campus.name), Campus.id)
                .all()
            )
            admins = {
                user.campus_id: user
                for user in session.query(User)
                .filter(
                    User.school_id == school.id,
                    User.role == UserRoles.ADMIN,
                    User.is_active.is_(True),
                )
                .all()
            }
        return [
            CampusSummary(
                campus=campus,
                admin=admins.get(campus.id),
                kpi=self._kpi(campus.id),
            )
            for campus in campuses
        ]

    def get_campus(self, campus_id: int) -> Campus:
        """One Campus of the School (for read-only drill-down routes)."""
        with self._session() as session:
            return self._get_campus(session, campus_id)

    def list_owners(self) -> list[User]:
        """The School's Owner accounts: active first, then by name."""
        with self._session() as session:
            school = self._get_school(session)
            return (
                session.query(User)
                .filter(
                    User.school_id == school.id,
                    User.role == UserRoles.OWNER,
                )
                .order_by(User.is_active.desc(), func.lower(User.name), User.id)
                .all()
            )

    def _kpi(self, campus_id: int) -> CampusKpi | None:
        """One Campus's current-month KPIs, or ``None`` without a report service.

        The report service is scoped by the request scope, so the Campus's data
        is read by running it under a Campus-scoped context.
        """
        if self._reports is None:
            return None
        today = date.today()
        campus_scope = RequestScope(
            user=None, school_id=self._school_id(), campus_id=campus_id
        )
        with scope_context(campus_scope):
            dashboard = self._reports.dashboard(today=today)
            paid = self._reports.paid_students(today.month, today.year)
        return CampusKpi(
            collected_cents=dashboard.collected_cents,
            expenses_cents=dashboard.expenses_cents,
            arrears_cents=dashboard.arrears_cents,
            expected_cents=paid.expected_cents,
            paid_cents=paid.collected_cents,
            active_student_count=dashboard.active_student_count,
        )

    # -- Campus lifecycle ----------------------------------------------------

    def create_campus(
        self,
        *,
        actor: User | None,
        name: str,
        address: str = "",
        phone: str = "",
        email: str = "",
        website: str = "",
        admin_name: str = "",
        admin_username: str = "",
        admin_password: str = "",
    ) -> Campus:
        """Create a Campus of the School, optionally with its first Campus Admin."""
        name = (name or "").strip()
        if not name:
            raise SchoolError("A Campus name is required.")
        admin_fields = (admin_name, admin_username, admin_password)
        if any(admin_fields) and not all(admin_fields):
            raise SchoolError("The Campus admin needs a name, username, and password.")
        admin_username = (admin_username or "").strip()

        with self._session() as session:
            school = self._get_school(session)
            if admin_username and self._username_taken(session, admin_username):
                raise UsernameTaken(
                    f"A user with the username '{admin_username}' already exists."
                )
            campus = Campus(
                school_id=school.id,
                name=name,
                address=address.strip() or None,
                phone=phone.strip() or None,
                email=email.strip() or None,
                website=website.strip() or None,
            )
            session.add(campus)
            session.flush()
            admin = None
            if admin_username:
                if not (admin_name or "").strip():
                    raise SchoolError("The Campus admin needs a name.")
                if not admin_password:
                    raise SchoolError("The Campus admin needs a password.")
                admin = User(
                    name=(admin_name or "").strip(),
                    username=admin_username,
                    password_hash=hash_password(admin_password),
                    role=UserRoles.ADMIN,
                    school_id=school.id,
                    campus_id=campus.id,
                )
                session.add(admin)
            session.commit()
            session.refresh(campus)
        self._log(
            user=actor,
            action=AuditActions.CAMPUS_CREATE,
            summary=f"Created Campus {campus.name}",
        )
        if admin is not None:
            self._log(
                user=actor,
                action=AuditActions.CAMPUS_ADMIN_ASSIGN,
                summary=f"Assigned {admin.name} ({admin.username}) as Campus admin of {campus.name}",
            )
        return campus

    def create_campus_admin(
        self, *, actor: User | None, campus_id: int, name: str, username: str, password: str
    ) -> User:
        """Assign a Campus Admin to a Campus (the ticket's "assigns Campus Admin")."""
        name = (name or "").strip()
        username = (username or "").strip()
        if not name or not username:
            raise SchoolError("Name and username are required.")
        if not password:
            raise SchoolError("A password is required.")
        with self._session() as session:
            campus = self._get_campus(session, campus_id)
            if campus.archived:
                raise SchoolError(f"Campus {campus.name} is archived.")
            if self._username_taken(session, username):
                raise UsernameTaken(f"A user with the username '{username}' already exists.")
            admin = User(
                name=name,
                username=username,
                password_hash=hash_password(password),
                role=UserRoles.ADMIN,
                school_id=campus.school_id,
                campus_id=campus.id,
            )
            session.add(admin)
            session.commit()
            session.refresh(admin)
        self._log(
            user=actor,
            action=AuditActions.CAMPUS_ADMIN_ASSIGN,
            summary=(
                f"Assigned {admin.name} ({admin.username}) as Campus admin of {campus.name}"
            ),
        )
        return admin

    def archive_campus(self, *, actor: User | None, campus_id: int) -> Campus:
        """Soft-delete a Campus: its history stays, its ``archived`` flag flips.

        The last active Campus cannot be archived, so the School is never left
        without a branch.
        """
        with self._session() as session:
            campus = self._get_campus(session, campus_id)
            if campus.archived:
                return campus
            if (
                not campus.archived
                and self._active_campus_count(session) <= 1
            ):
                raise LastActiveCampus(
                    "This is the School's only active Campus. Create another "
                    "Campus before archiving it."
                )
            campus.archived = True
            session.commit()
            session.refresh(campus)
        self._log(
            user=actor,
            action=AuditActions.CAMPUS_ARCHIVE,
            summary=f"Archived Campus {campus.name}",
        )
        return campus

    # -- Owner accounts ------------------------------------------------------

    def _get_owner(self, session: Session, user_id: int) -> User:
        school = self._get_school(session)
        user = (
            session.query(User)
            .filter(
                User.id == user_id,
                User.school_id == school.id,
                User.role == UserRoles.OWNER,
            )
            .one_or_none()
        )
        if user is None:
            raise OwnerNotFound(f"No Owner account with id {user_id} exists.")
        return user

    def create_owner(self, *, actor: User | None, name: str, username: str, password: str) -> User:
        """Create a School-bound Owner account (read-only by design)."""
        name = (name or "").strip()
        username = (username or "").strip()
        if not name or not username:
            raise SchoolError("Name and username are required.")
        if not password:
            raise SchoolError("A password is required.")
        with self._session() as session:
            school = self._get_school(session)
            if self._username_taken(session, username):
                raise UsernameTaken(f"A user with the username '{username}' already exists.")
            owner = User(
                name=name,
                username=username,
                password_hash=hash_password(password),
                role=UserRoles.OWNER,
                school_id=school.id,
                campus_id=None,
            )
            session.add(owner)
            session.commit()
            session.refresh(owner)
        self._log(
            user=actor,
            action=AuditActions.OWNER_CREATE,
            summary=f"Created Owner account {owner.username} ({owner.name})",
        )
        return owner

    def disable_owner(self, *, actor: User | None, user_id: int) -> User:
        """Disable an Owner account. Refuses self-disable (an Owner actor)."""
        with self._session() as session:
            owner = self._get_owner(session, user_id)
            if actor is not None and owner.id == actor.id:
                raise SchoolError("You cannot disable your own account.")
            if not owner.is_active:
                return owner
            owner.is_active = False
            session.commit()
            session.refresh(owner)
        self._log(
            user=actor,
            action=AuditActions.OWNER_DISABLE,
            summary=f"Disabled Owner account {owner.username} ({owner.name})",
        )
        return owner

    def enable_owner(self, *, actor: User | None, user_id: int) -> User:
        """Re-enable a disabled Owner account. No-op (and unaudited) if active."""
        with self._session() as session:
            owner = self._get_owner(session, user_id)
            if owner.is_active:
                return owner
            owner.is_active = True
            session.commit()
            session.refresh(owner)
        self._log(
            user=actor,
            action=AuditActions.OWNER_ENABLE,
            summary=f"Enabled Owner account {owner.username} ({owner.name})",
        )
        return owner

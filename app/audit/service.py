"""Audit service layer: append-only entries and scoped browsing.

Every auditable action across the app is recorded through :meth:`AuditService.log`
with the acting user, a timestamp, and a readable summary. The log is append-only
by design: this service exposes no update or delete operations, and no route in
the app offers one. Future features (payments, expenses, fee templates,
waivers, configuration) call ``log`` at the same seam.

**Campus scoping (multi-school ticket 06):** an entry is stamped with the acting
scope's Campus at write time — campus-level actions (payments, expenses,
students, classes, fee templates, waivers, closed months, branding) land under
the Campus they happened in, while school-level actions (Campus creation, admin
assignment, owner management, setup) carry a NULL Campus (MD-2). Browsing uses
:func:`audit_scope_filter`: a Campus-bound scope sees its own Campus's entries
plus the shared NULL bucket (system and school-level events), and a School-bound
scope sees every Campus in its School plus that same bucket. In the single-school
deployment every entry is visible either through the one implicit Campus or
through the NULL bucket, so the audit page behaves exactly as before.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from ..db import Database
from ..models import AuditLogEntry, User
from ..tenants.scope import audit_scope_filter, scope


class AuditActions:
    """Action names recorded so far. Later features add their own constants here."""

    SETUP = "setup"
    LOGIN = "login"
    LOGOUT = "logout"

    # Classes.
    CLASS_CREATE = "class_create"
    CLASS_RENAME = "class_rename"
    CLASS_STATUS = "class_status"

    # Fee templates & class defaults (fee-billing rework).
    TEMPLATE_CREATE = "template_create"
    TEMPLATE_RENAME = "template_rename"
    TEMPLATE_AMOUNT_CHANGE = "template_amount_change"
    TEMPLATE_ARCHIVE = "template_archive"
    TEMPLATE_RESTORE = "template_restore"
    CLASS_DEFAULT_TEMPLATE = "class_default_template"

    # Students.
    STUDENT_ADD = "student_add"
    STUDENT_UPDATE = "student_update"
    STUDENT_ARCHIVE = "student_archive"
    STUDENT_RESTORE = "student_restore"
    STUDENT_IMPORT = "student_import"
    STUDENT_AMOUNT_CHANGE = "student_amount_change"
    STUDENT_TEMPLATE = "student_template"

    # Per-(student, month) waivers.
    WAIVER_ADD = "waiver_add"

    # School-wide closed months.
    CLOSED_MONTH_ADD = "closed_month_add"
    CLOSED_MONTH_REMOVE = "closed_month_remove"

    # Payments & receipts.
    PAYMENT_RECORD = "payment_record"

    # Expenses & categories.
    EXPENSE_CATEGORY_ADD = "expense_category_add"
    EXPENSE_CATEGORY_RENAME = "expense_category_rename"
    EXPENSE_CATEGORY_REMOVE = "expense_category_remove"
    EXPENSE_RECORD = "expense_record"

    # System admin — user accounts.
    USER_CREATE = "user_create"
    USER_DISABLE = "user_disable"
    USER_ENABLE = "user_enable"
    USER_PASSWORD_RESET = "user_password_reset"

    # School profile & branding.
    PROFILE_UPDATE = "profile_update"
    PROFILE_LOGO_UPLOAD = "profile_logo_upload"
    PROFILE_LOGO_REMOVE = "profile_logo_remove"

    # System admin — backups & shutdown.
    BACKUP_AUTOMATIC = "backup_automatic"
    BACKUP_MANUAL = "backup_manual"
    SHUTDOWN = "shutdown"

    # School level (ticket 08) — recorded school-wide (NULL campus, MD-2).
    CAMPUS_CREATE = "campus_create"
    CAMPUS_ARCHIVE = "campus_archive"
    CAMPUS_ADMIN_ASSIGN = "campus_admin_assign"
    OWNER_CREATE = "owner_create"
    OWNER_DISABLE = "owner_disable"
    OWNER_ENABLE = "owner_enable"

    LABELS = {
        SETUP: "Setup",
        LOGIN: "Login",
        LOGOUT: "Logout",
        CLASS_CREATE: "Class created",
        CLASS_RENAME: "Class renamed",
        CLASS_STATUS: "Class status changed",
        TEMPLATE_CREATE: "Fee template created",
        TEMPLATE_RENAME: "Fee template renamed",
        TEMPLATE_AMOUNT_CHANGE: "Fee template amount changed",
        TEMPLATE_ARCHIVE: "Fee template archived",
        TEMPLATE_RESTORE: "Fee template restored",
        CLASS_DEFAULT_TEMPLATE: "Class default template changed",
        STUDENT_ADD: "Student added",
        STUDENT_UPDATE: "Student updated",
        STUDENT_ARCHIVE: "Student archived",
        STUDENT_RESTORE: "Student restored",
        STUDENT_IMPORT: "Students imported",
        STUDENT_AMOUNT_CHANGE: "Student monthly amount changed",
        STUDENT_TEMPLATE: "Student fee template changed",
        WAIVER_ADD: "Waiver applied",
        CLOSED_MONTH_ADD: "Month closed",
        CLOSED_MONTH_REMOVE: "Month reopened",
        PAYMENT_RECORD: "Payment recorded",
        EXPENSE_CATEGORY_ADD: "Expense category added",
        EXPENSE_CATEGORY_RENAME: "Expense category renamed",
        EXPENSE_CATEGORY_REMOVE: "Expense category removed",
        EXPENSE_RECORD: "Expense recorded",
        USER_CREATE: "User created",
        USER_DISABLE: "User disabled",
        USER_ENABLE: "User enabled",
        USER_PASSWORD_RESET: "Password reset",
        PROFILE_UPDATE: "School profile updated",
        PROFILE_LOGO_UPLOAD: "School logo uploaded",
        PROFILE_LOGO_REMOVE: "School logo removed",
        BACKUP_AUTOMATIC: "Automatic backup",
        BACKUP_MANUAL: "Manual backup",
        SHUTDOWN: "App shut down",
        CAMPUS_CREATE: "Campus created",
        CAMPUS_ARCHIVE: "Campus archived",
        CAMPUS_ADMIN_ASSIGN: "Campus admin assigned",
        OWNER_CREATE: "Owner account created",
        OWNER_DISABLE: "Owner account disabled",
        OWNER_ENABLE: "Owner account enabled",
    }


class AuditError(Exception):
    """Rejected input while recording an audit entry."""


class AuditService:
    """Audit business rules. Each method is one unit of work on its own session."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _session(self) -> Session:
        return self._db.session()

    def add(
        self,
        session: Session,
        *,
        user: User | None,
        action: str,
        summary: str,
    ) -> AuditLogEntry:
        """Add one audit entry to an already-open session; the caller commits.

        Lets a service record its audit entry atomically with its own change
        (e.g. a payment) in a single transaction, so the entry cannot be lost
        if the caller's commit succeeds.
        """
        action = (action or "").strip()
        summary = (summary or "").strip()
        if not action:
            raise AuditError("An action name is required.")
        if not summary:
            raise AuditError("A summary is required.")

        cur = scope()
        entry = AuditLogEntry(
            user_id=user.id if user is not None else None,
            # The acting scope's Campus: campus-level actions are tagged to the
            # Campus they happened in; school-level and system actions (and any
            # write outside a request scope) stay NULL (MD-2).
            campus_id=cur.campus_id if cur is not None else None,
            action=action,
            summary=summary,
        )
        session.add(entry)
        return entry

    def log(
        self,
        *,
        user: User | None,
        action: str,
        summary: str,
    ) -> AuditLogEntry:
        """Append one immutable audit entry on its own transaction.

        ``user=None`` marks a system-level event (e.g. the first-admin setup,
        which runs before any account exists). Services that need the entry
        atomic with their own write use :meth:`add` instead.
        """
        with self._session() as session:
            entry = self.add(session, user=user, action=action, summary=summary)
            session.commit()
            session.refresh(entry)
        return entry

    def list_entries(
        self,
        *,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """Browse entries the acting scope may see, most recent first.

        A Campus-bound scope sees its own Campus's entries plus the NULL-campus
        bucket (system and school-level events); a School-bound scope sees every
        Campus in its School plus that bucket. Optionally filtered by action.
        """
        with self._session() as session:
            query = session.query(AuditLogEntry).options(joinedload(AuditLogEntry.user))
            cur = scope()
            if cur is not None:
                query = query.filter(
                    audit_scope_filter(session, cur, AuditLogEntry.campus_id)
                )
            if action:
                query = query.filter(AuditLogEntry.action == action)
            return (
                query.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

    def count(self, *, action: str | None = None) -> int:
        """Total matching entries the acting scope may see, for pagination."""
        with self._session() as session:
            query = session.query(AuditLogEntry)
            cur = scope()
            if cur is not None:
                query = query.filter(
                    audit_scope_filter(session, cur, AuditLogEntry.campus_id)
                )
            if action:
                query = query.filter(AuditLogEntry.action == action)
            return query.count()

    def list_actions(self) -> list[str]:
        """Distinct action names the acting scope may see, sorted (dropdown)."""
        with self._session() as session:
            query = session.query(AuditLogEntry.action)
            cur = scope()
            if cur is not None:
                query = query.filter(
                    audit_scope_filter(session, cur, AuditLogEntry.campus_id)
                )
            rows = query.distinct().all()
            return sorted(row[0] for row in rows)

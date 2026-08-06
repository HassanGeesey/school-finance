"""Audit service layer: append-only entries and admin browsing.

Every auditable action across the app is recorded through :meth:`AuditService.log`
with the acting user, a timestamp, and a readable summary. The log is append-only
by design: this service exposes no update or delete operations, and no route in
the app offers one. Future features (payments, expenses, fee generation,
adjustments, configuration) call ``log`` at the same seam.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from ..db import Database
from ..models import AuditLogEntry, User


class AuditActions:
    """Action names recorded so far. Later features add their own constants here."""

    SETUP = "setup"
    LOGIN = "login"
    LOGOUT = "logout"

    # Classes & fee structures.
    CLASS_CREATE = "class_create"
    CLASS_RENAME = "class_rename"
    CLASS_STATUS = "class_status"
    FEE_ITEM_ADD = "fee_item_add"
    FEE_ITEM_UPDATE = "fee_item_update"
    FEE_ITEM_REMOVE = "fee_item_remove"

    # Students.
    STUDENT_ADD = "student_add"
    STUDENT_UPDATE = "student_update"
    STUDENT_ARCHIVE = "student_archive"
    STUDENT_RESTORE = "student_restore"
    STUDENT_IMPORT = "student_import"

    # Monthly fee generation.
    FEE_GENERATE = "fee_generate"

    # Per-student month adjustments (extras/waivers).
    ADJUSTMENT_ADD = "adjustment_add"

    # Payments & receipts.
    PAYMENT_RECORD = "payment_record"

    LABELS = {
        SETUP: "Setup",
        LOGIN: "Login",
        LOGOUT: "Logout",
        CLASS_CREATE: "Class created",
        CLASS_RENAME: "Class renamed",
        CLASS_STATUS: "Class status changed",
        FEE_ITEM_ADD: "Fee item added",
        FEE_ITEM_UPDATE: "Fee item updated",
        FEE_ITEM_REMOVE: "Fee item removed",
        STUDENT_ADD: "Student added",
        STUDENT_UPDATE: "Student updated",
        STUDENT_ARCHIVE: "Student archived",
        STUDENT_RESTORE: "Student restored",
        STUDENT_IMPORT: "Students imported",
        FEE_GENERATE: "Monthly fees generated",
        ADJUSTMENT_ADD: "Adjustment made",
        PAYMENT_RECORD: "Payment recorded",
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

        entry = AuditLogEntry(
            user_id=user.id if user is not None else None,
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
        """Browse entries, most recent first, optionally filtered by action."""
        with self._session() as session:
            query = session.query(AuditLogEntry).options(joinedload(AuditLogEntry.user))
            if action:
                query = query.filter(AuditLogEntry.action == action)
            return (
                query.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

    def count(self, *, action: str | None = None) -> int:
        """Total matching entries, used for pagination."""
        with self._session() as session:
            query = session.query(AuditLogEntry)
            if action:
                query = query.filter(AuditLogEntry.action == action)
            return query.count()

    def list_actions(self) -> list[str]:
        """Distinct action names present in the log, sorted (filter dropdown)."""
        with self._session() as session:
            rows = session.query(AuditLogEntry.action).distinct().all()
            return sorted(row[0] for row in rows)

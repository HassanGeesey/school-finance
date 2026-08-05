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

    LABELS = {
        SETUP: "Setup",
        LOGIN: "Login",
        LOGOUT: "Logout",
    }


class AuditError(Exception):
    """Rejected input while recording an audit entry."""


class AuditService:
    """Audit business rules. Each method is one unit of work on its own session."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _session(self) -> Session:
        return self._db.session()

    def log(
        self,
        *,
        user: User | None,
        action: str,
        summary: str,
    ) -> AuditLogEntry:
        """Append one immutable audit entry.

        ``user=None`` marks a system-level event (e.g. the first-admin setup,
        which runs before any account exists).
        """
        action = (action or "").strip()
        summary = (summary or "").strip()
        if not action:
            raise AuditError("An action name is required.")
        if not summary:
            raise AuditError("A summary is required.")

        with self._session() as session:
            entry = AuditLogEntry(
                user_id=user.id if user is not None else None,
                action=action,
                summary=summary,
            )
            session.add(entry)
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

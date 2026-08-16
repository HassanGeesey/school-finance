"""Per-request tenant scope (multi-school): the campus a request may see.

A request-scoped :class:`RequestScope` is derived from the authenticated user
(MD-2: Admin/Finance scope by ``campus_id``; Superadmin/Owner scope by
``school_id``) and set in a context variable by the session middleware in
``app.main``. Services read it through :func:`scope` to filter reads and stamp
``campus_id`` on writes, so route signatures stay unchanged while every
operational table becomes tenant-aware.

Outside an HTTP request (pure service tests, direct service calls, the setup
path) the context variable is unset and :func:`scope` returns ``None``: reads
are unfiltered and writes are left unstamped, exactly the legacy single-school
behavior (ticket 01 is additive). Rows with a NULL ``campus_id`` are legacy
rows created before scoping; they stay visible to every user of the deployment
until the hardening ticket makes the columns non-nullable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Campus, User, UserRoles

__all__ = [
    "RequestScope",
    "campus_for_write",
    "in_scope",
    "scope",
    "scope_context",
    "scoped_campus_filter",
]


@dataclass(frozen=True)
class RequestScope:
    """The tenant context of one request, resolved from the acting user.

    ``campus_id`` is set for Campus-bound roles (Admin/Finance); ``school_id``
    is set for School-bound roles (Superadmin/Owner). Exactly one is
    meaningful; the other stays ``None``.
    """

    user: User | None
    school_id: int | None
    campus_id: int | None

    @classmethod
    def for_user(cls, user: User | None) -> "RequestScope | None":
        """Resolve a user's role into its tenant scope.

        ``None`` when there is no user (anonymous requests and system-level
        work run unscoped), or when the user carries no tenant columns at all —
        the legacy single-school users (finance officers created before the
        multi-school work) stay unscoped so nothing regresses. All four roles
        are recognized (ticket 03): the two Campus-bound roles carry the
        user's campus, and the two School-bound roles carry the user's school.
        """
        if user is None:
            return None
        if user.role in (UserRoles.ADMIN, UserRoles.FINANCE):
            campus_id, school_id = user.campus_id, user.school_id
        else:
            campus_id, school_id = None, user.school_id
        if campus_id is None and school_id is None:
            return None
        return cls(user=user, school_id=school_id, campus_id=campus_id)


_scope_var: ContextVar[RequestScope | None] = ContextVar(
    "school_finance_request_scope", default=None
)


def scope() -> RequestScope | None:
    """The current request's scope, or ``None`` when no scope is set."""
    return _scope_var.get()


@contextmanager
def scope_context(scope_: RequestScope | None) -> Iterator[None]:
    """Set the scope for the duration of the block (middleware and tests)."""
    token = _scope_var.set(scope_)
    try:
        yield
    finally:
        _scope_var.reset(token)


def _visible_campus_ids(session: Session, scope_: RequestScope) -> list[int]:
    """The campus ids the scope may see.

    A Campus-bound scope sees exactly its campus; a School-bound scope sees
    every campus of its school; an unscoped-but-not-None scope (a user with no
    tenant columns yet) sees nothing.
    """
    if scope_.campus_id is not None:
        return [scope_.campus_id]
    if scope_.school_id is not None:
        return [
            campus_id
            for (campus_id,) in (
                session.query(Campus.id).filter(Campus.school_id == scope_.school_id).all()
            )
        ]
    return []


def scoped_campus_filter(session: Session, scope_: RequestScope, column):
    """A SQLAlchemy filter limiting ``column`` to the scope's campuses.

    Legacy NULL-campus rows are included alongside the scope's campuses, so
    pre-scoping data stays visible within the deployment.
    """
    ids = _visible_campus_ids(session, scope_)
    return or_(column.in_(ids), column.is_(None))


def in_scope(session: Session, scope_: RequestScope, campus_id: int | None) -> bool:
    """Whether a row whose campus is ``campus_id`` is visible to the scope.

    Legacy NULL rows are visible to every scope.
    """
    if campus_id is None:
        return True
    return campus_id in _visible_campus_ids(session, scope_)


def campus_for_write(scope_: RequestScope | None) -> int | None:
    """The ``campus_id`` a new operational row should be stamped with.

    ``None`` when unscoped (no request, or a School-bound role that never
    writes operational data).
    """
    return scope_.campus_id if scope_ is not None else None

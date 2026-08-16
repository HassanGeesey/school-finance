"""Per-request tenant scope (multi-school): the campus a request may see.

A request-scoped :class:`RequestScope` is derived from the authenticated user
(MD-2: Admin/Finance scope by ``campus_id``; Superadmin/Owner scope by
``school_id``) and set in a context variable by the session middleware in
``app.main``. Services read it through :func:`scope` to filter reads and stamp
``campus_id`` on writes, so route signatures stay unchanged while every
operational table is tenant-aware.

The tenant layer is mandatory (ticket 09): every operational row carries a
``campus_id`` (NOT NULL) and every operational read/write runs inside a scope.
:func:`require_scope` and :func:`campus_for_write` raise
:class:`TenantScopeError` when no scope is available, and
:func:`scoped_campus_filter` narrows every query to the scope's campuses, so an
unscoped query path fails loudly instead of leaking. The users table (school-
or campus-scoped via its own columns) and the audit log (school-level entries
stay NULL, MD-2) are the two deliberate carve-outs — see :func:`audit_scope_filter`.
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
    "TenantScopeError",
    "audit_scope_filter",
    "campus_for_write",
    "in_scope",
    "require_scope",
    "scope",
    "scope_context",
    "scoped_campus_filter",
]


class TenantScopeError(RuntimeError):
    """A service call required a tenant scope but none was available."""


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

        ``None`` when there is no user (anonymous requests) or when the user
        carries no tenant columns at all — those users have no campus. All four
        roles are recognized (ticket 03): the two Campus-bound roles carry the
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


def require_scope() -> RequestScope:
    """The current request's scope — :class:`TenantScopeError` when unset."""
    current = _scope_var.get()
    if current is None:
        raise TenantScopeError("no tenant scope on this request")
    return current


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
    every campus of its school.
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


def scoped_campus_filter(session: Session, scope_: RequestScope | None, column):
    """A SQLAlchemy filter limiting ``column`` to the scope's campuses.

    Operational rows always carry a campus (ticket 09), so an unscoped call is
    a bug and raises rather than leaking or silently returning empty.
    """
    if scope_ is None:
        raise TenantScopeError("unscoped query: a scope is required")
    return column.in_(_visible_campus_ids(session, scope_))


def audit_scope_filter(session: Session, scope_: RequestScope | None, column):
    """Audit browsing filter: the scope's campuses plus the NULL-campus bucket.

    School-level and system audit entries are recorded school-wide (MD-2) and
    carry a NULL Campus by design; they stay visible alongside the scope's
    Campus entries so the single-school audit page behaves exactly as before.
    """
    if scope_ is None:
        raise TenantScopeError("unscoped query: a scope is required")
    return or_(column.in_(_visible_campus_ids(session, scope_)), column.is_(None))


def in_scope(session: Session, scope_: RequestScope | None, campus_id: int | None) -> bool:
    """Whether a row whose campus is ``campus_id`` is visible to the scope.

    Rows always carry a campus (ticket 09); without a scope nothing is visible.
    """
    if scope_ is None:
        return False
    if campus_id is None:
        return False
    return campus_id in _visible_campus_ids(session, scope_)


def campus_for_write(scope_: RequestScope | None) -> int:
    """The ``campus_id`` a new operational row must be stamped with.

    Requires a Campus-bound scope: unscoped requests and School-bound roles
    (Superadmin/Owner) never write operational data directly and raise.
    """
    if scope_ is None or scope_.campus_id is None:
        raise TenantScopeError("operational writes require a campus-scoped request")
    return scope_.campus_id

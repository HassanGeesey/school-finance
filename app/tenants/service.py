"""Tenant bootstrap (multi-school): the implicit School + first Campus.

Multi-school ticket 01 is additive only — nothing is torn out — but a fresh
database gets one School with one Campus silently, so every operational row
already has a tenant home before the scoping tickets (02+) start writing
``campus_id``. On the offline path this is invisible: the setup wizard, pages,
and roles behave exactly as before, and the app's data simply lives in that
implicit School + Campus (UR-15, C-5). No hard deletes: a Campus's ``archived``
flag is the only way a branch goes away.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import Database
from ..models import Campus, School


class TenantService:
    """Tenant business rules. Each method is one unit of work on its own session."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _session(self) -> Session:
        return self._db.session()

    def ensure_bootstrap(self) -> School:
        """Create the implicit School and its first Campus when missing.

        Idempotent: a fresh database gets exactly one School with one Campus; a
        database with a School but no Campus (partial state) gets the missing
        Campus added. Existing tenants are never duplicated or rewritten.
        """
        with self._session() as session:
            school, _campus = ensure_bootstrap_on(session)
            session.commit()
            session.refresh(school)
            return school


def ensure_bootstrap_on(session: Session) -> tuple[School, Campus]:
    """Create the implicit School and its first Campus inside an open session.

    The caller commits. Used by the tenant service (its own unit of work) and
    by the setup wizard, which needs the implicit School + Campus to bind the
    first Admin to them in the same transaction.
    """
    school = session.query(School).first()
    if school is None:
        school = School(name="")
        session.add(school)
        session.flush()
    campus = session.query(Campus).filter(Campus.school_id == school.id).first()
    if campus is None:
        campus = Campus(school_id=school.id, name="")
        session.add(campus)
        session.flush()
    return school, campus

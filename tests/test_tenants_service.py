"""Tenant bootstrap (multi-school ticket 01): a fresh install gets one implicit
School with one Campus, silently — the offline first run behaves exactly as
today while its data gains a tenant home.
"""

from app.models import Campus, School
from app.tenants.service import TenantService


def test_bootstrap_creates_one_school_with_one_campus(db):
    school = TenantService(db).ensure_bootstrap()

    with db.session() as session:
        assert session.query(School).count() == 1
        assert session.query(Campus).count() == 1
        campus = session.query(Campus).one()
        assert campus.school_id == school.id
        assert campus.archived is False


def test_bootstrap_is_idempotent(db):
    service = TenantService(db)
    service.ensure_bootstrap()
    service.ensure_bootstrap()

    with db.session() as session:
        assert session.query(School).count() == 1
        assert session.query(Campus).count() == 1


def test_bootstrap_repairs_a_school_without_a_campus(db):
    with db.session() as session:
        session.add(School(name="Sunrise Primary"))
        session.commit()

    school = TenantService(db).ensure_bootstrap()

    with db.session() as session:
        assert session.query(School).count() == 1
        assert session.query(Campus).count() == 1
        assert session.query(Campus).one().school_id == school.id


def test_bootstrap_never_duplicates_an_existing_tenant(db):
    with db.session() as session:
        session.add(School(name="Sunrise Primary"))
        session.commit()

    first = TenantService(db).ensure_bootstrap()
    with db.session() as session:
        assert session.query(School).count() == 1
        assert session.query(Campus).count() == 1
        assert session.query(School).one().name == "Sunrise Primary"
        assert first.name == "Sunrise Primary"

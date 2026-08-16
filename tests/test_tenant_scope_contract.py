"""Tenant-layer contract (multi-school ticket 09): scope is mandatory.

Service reads and writes without a request scope are bugs — they must fail
loudly (:class:`TenantScopeError`) rather than leak or run unscoped. The
schema-level NOT NULL guarantee lives in ``test_schema.py``.
"""

import pytest

from app.audit.service import AuditService
from app.classes.service import ClassService
from app.fees.service import TemplateService
from app.tenants.scope import (
    RequestScope,
    TenantScopeError,
    campus_for_write,
    in_scope,
    require_scope,
    scope_context,
    scoped_campus_filter,
)


@pytest.fixture()
def classes(db) -> ClassService:
    return ClassService(db, audit=AuditService(db))


@pytest.fixture()
def templates(db) -> TemplateService:
    return TemplateService(db, audit=AuditService(db))


def test_require_scope_raises_when_no_scope_is_set():
    with pytest.raises(TenantScopeError):
        require_scope()


def test_require_scope_returns_the_scope_inside_a_context(db, session):
    with db.session() as session:
        from app.models import School, Campus

        school = School(name="S")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="C")
        session.add(campus)
        session.commit()
        scope_ = RequestScope(user=None, school_id=school.id, campus_id=campus.id)

    with scope_context(scope_):
        assert require_scope() == scope_


def test_campus_for_write_raises_when_unscoped():
    with pytest.raises(TenantScopeError):
        campus_for_write(None)


def test_campus_for_write_raises_for_a_school_bound_scope():
    scope_ = RequestScope(user=None, school_id=1, campus_id=None)
    with pytest.raises(TenantScopeError):
        campus_for_write(scope_)


def test_campus_for_write_returns_the_campus_for_a_campus_bound_scope():
    scope_ = RequestScope(user=None, school_id=1, campus_id=7)
    assert campus_for_write(scope_) == 7


def test_in_scope_returns_false_when_unscoped(db, session):
    with db.session() as session:
        from app.models import School, Campus

        school = School(name="S")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="C")
        session.add(campus)
        session.commit()

        assert in_scope(session, None, campus.id) is False
        assert in_scope(session, None, None) is False


def test_scoped_campus_filter_raises_when_unscoped(db, session):
    from app.models import School, Campus, Class

    school = School(name="S")
    session.add(school)
    session.flush()
    campus = Campus(school_id=school.id, name="C")
    session.add(campus)
    session.commit()

    with pytest.raises(TenantScopeError):
        scoped_campus_filter(session, None, Class.campus_id)


def test_a_read_without_a_scope_raises(classes, db, session):
    from app.models import School, Campus, Class

    school = School(name="S")
    session.add(school)
    session.flush()
    campus = Campus(school_id=school.id, name="C")
    session.add(campus)
    session.commit()
    session.add(Class(name="Grade 1", campus_id=campus.id))
    session.commit()

    # No scope_context set: the service query is a bug and must fail loudly.
    with pytest.raises(TenantScopeError):
        classes.list_class_summaries()


def test_a_write_without_a_scope_raises(classes, db):
    with pytest.raises(TenantScopeError):
        classes.create_class(user=None, name="Grade 1")


def test_a_read_inside_a_scope_is_scoped(classes, db, session):
    from app.models import School, Campus, Class

    school = School(name="S")
    session.add(school)
    session.flush()
    campus = Campus(school_id=school.id, name="C")
    session.add(campus)
    session.commit()
    session.add(Class(name="Grade 1", campus_id=campus.id))
    session.commit()
    scope_ = RequestScope(user=None, school_id=school.id, campus_id=campus.id)

    with scope_context(scope_):
        rows = classes.list_class_summaries()

    assert [row.cls.name for row in rows] == ["Grade 1"]

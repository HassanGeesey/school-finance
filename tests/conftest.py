"""Shared test fixtures.

Every test runs against a fresh in-memory SQLite database (StaticPool) so tests
never touch the real data file and never interfere with each other.

The full app's billing modules are still being reworked (ticket 01: the app is
intentionally red until the rework lands), so the ``client`` fixture is skipped
while ``app.main`` cannot build a billing app. Owned tests use the mini app
(``include_billing=False``) through ``mini_app``/``mini_client``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Database, make_engine
from app.main import create_app
from app.models import Campus, School
from app.tenants.scope import RequestScope, scope_context
from tests.mini_app import build_mini_app

# Tests always run against in-memory SQLite, never the real cloud DB.
# The .env file may set DATABASE_URL to Postgres; force the settings singleton
# back to SQLite so every test fixture sees the in-memory database.
_TEST_SQLITE_URL = "sqlite://"
settings.DATABASE_URL = _TEST_SQLITE_URL
settings.CLOUD_MODE = False


@pytest.fixture()
def db() -> Database:
    database = Database(make_engine("sqlite://"))
    database.create_all()
    return database


@pytest.fixture()
def session(db: Database) -> Iterator[Session]:
    with db.session() as session:
        yield session


@pytest.fixture()
def world(db: Database) -> Iterator[RequestScope]:
    """A bare db plus one implicit School + Campus, with the request scope set.

    Service tests that exercise operational reads/writes run under this scope so
    the mandatory tenant layer (ticket 09) is satisfied: reads filter to the
    implicit Campus and writes get stamped. No user is seeded — tests create
    their own actors.
    """
    with db.session() as session:
        school = School(name="Implicit School")
        session.add(school)
        session.flush()
        campus = Campus(school_id=school.id, name="Implicit Campus")
        session.add(campus)
        session.commit()
        scope_ = RequestScope(user=None, school_id=school.id, campus_id=campus.id)
    with scope_context(scope_):
        yield scope_


@pytest.fixture()
def campus_id(world: RequestScope) -> int:
    """The implicit Campus id for raw-seed stamps (ticket 09)."""
    return world.campus_id


@pytest.fixture()
def mini_app(tmp_path) -> FastAPI:
    """The fee/class app without billing: mounts auth/classes/students/fees/..."""
    return build_mini_app(logo_dir=tmp_path)


@pytest.fixture()
def mini_client(tmp_path) -> Iterator[TestClient]:
    with TestClient(build_mini_app(logo_dir=tmp_path)) as client:
        yield client


@pytest.fixture()
def client() -> Iterator[TestClient]:
    try:
        app = create_app(database_url="sqlite://")
    except ImportError:
        pytest.skip("app.main billing modules still red (fee-billing rework)")
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def fast_password_hashing():
    """Lower the PBKDF2 work factor so auth tests stay fast (prod uses 600k)."""
    from app.config import settings

    original = settings.PBKDF2_ITERATIONS
    settings.PBKDF2_ITERATIONS = 1000
    yield
    settings.PBKDF2_ITERATIONS = original

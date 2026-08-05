"""Shared test fixtures.

Every test runs against a fresh in-memory SQLite database (StaticPool) so tests
never touch the real data file and never interfere with each other.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import Database, make_engine
from app.main import create_app


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
def client() -> Iterator[TestClient]:
    app = create_app(database_url="sqlite://")
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

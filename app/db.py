"""Database wiring: engine creation, session factory, schema initialisation.

Tests use an in-memory SQLite database; production uses a single SQLite file.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def make_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the given URL.

    SQLite gets ``check_same_thread=False`` (FastAPI runs handlers on a thread
    pool) and, for in-memory databases, a :class:`StaticPool` so every session
    shares the single in-memory connection.
    """
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        is_memory = ":memory:" in database_url or database_url in ("sqlite://", "sqlite+pysqlite://")
        poolclass = StaticPool if is_memory else None
        return create_engine(database_url, connect_args=connect_args, poolclass=poolclass)
    return create_engine(database_url)


class Database:
    """Holds an engine and a session factory bound to one database."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_all(self) -> None:
        """Create all tables defined by the domain model if missing."""
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._session_factory()

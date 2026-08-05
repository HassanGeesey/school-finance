"""Shared FastAPI dependencies used across feature routes."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    """Provide a database session to a route, committed/closed on exit."""
    with request.app.state.db.session() as session:
        yield session

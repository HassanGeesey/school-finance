"""Mini app factory for tests: the reworked slices without billing.

The full app (``app.main.create_app`` with ``include_billing=True``) still cannot
import its payments/arrears/reports modules until their rework tickets land, so
the owned fee/class tests build a non-billing app instead. ``build_mini_app`` is
a thin wrapper around the real factory: in-memory SQLite, a no-op shutdown
stopper, and an explicit temp logo directory.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.main import create_app


def build_mini_app(logo_dir: Path | None = None) -> FastAPI:
    return create_app(
        database_url="sqlite://",
        include_billing=False,
        shutdown_stopper=lambda: None,
        logo_dir=logo_dir,
    )

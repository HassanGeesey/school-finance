"""Centralised configuration for the school finance app.

Everything that varies per environment (paths, URLs, secrets) lives here so the
rest of the app reads from one place.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    APP_NAME = "School Finance"
    VERSION = "0.1.0"

    # Overridable via environment for tests/portable installs.
    DATA_DIR = Path(os.environ.get("SCHOOL_FINANCE_DATA", str(BASE_DIR / "data")))
    DB_PATH = DATA_DIR / "school_finance.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"

    STATIC_DIR = BASE_DIR / "app" / "static"
    TEMPLATES_DIR = BASE_DIR / "app" / "templates"


settings = Settings()

"""System routes end-to-end: manual backup, startup backup, and in-app shutdown.

Route-level smoke tests of the thin adapters + templates. Backup file mechanics
(copy, rotation, ordering) live in ``test_system_service.py``. These tests use
an app built with a temp backup source and a recording shutdown stopper so they
never stop the test runner or touch the real data file.
"""

import json
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audit.service import AuditActions
from app.main import create_app
from app.models import AuditLogEntry

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def _db(client):
    return cast(FastAPI, client.app).state.db


def audit_entries(client, action):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


@pytest.fixture()
def backup_app(tmp_path):
    source = tmp_path / "school_finance.db"
    source.write_bytes(b"sqlite-bytes")
    backup_dir = tmp_path / "backups"
    stopped = []
    app = create_app(
        database_url="sqlite://",
        backup_source=source,
        backup_dir=backup_dir,
        shutdown_stopper=lambda: stopped.append(True),
    )
    with TestClient(app) as client:
        yield client, backup_dir, stopped


@pytest.fixture()
def broken_backup_app(tmp_path):
    stopped = []
    app = create_app(
        database_url="sqlite://",
        backup_source=tmp_path / "missing.db",
        backup_dir=tmp_path / "backups",
        shutdown_stopper=lambda: stopped.append(True),
    )
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Role gating
# ---------------------------------------------------------------------------


def test_backup_now_requires_login(client):
    setup_admin(client)

    response = client.post("/system/backup", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_backup_now_requires_admin(backup_app):
    client, _backup_dir, _stopped = backup_app
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/system/backup",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 403


def test_shutdown_requires_admin(backup_app):
    client, _backup_dir, _stopped = backup_app
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post("/system/shutdown")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


def test_startup_backup_is_created_and_audited(backup_app):
    client, backup_dir, _stopped = backup_app
    authenticated_admin(client)

    assert len(list(backup_dir.iterdir())) == 1
    assert len(audit_entries(client, AuditActions.BACKUP_AUTOMATIC)) == 1


def test_admin_can_create_a_manual_backup(backup_app):
    client, backup_dir, _stopped = backup_app
    authenticated_admin(client)

    response = client.post(
        "/system/backup",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "toast" in response.headers["HX-Trigger"]
    assert len(list(backup_dir.iterdir())) == 2
    assert len(audit_entries(client, AuditActions.BACKUP_MANUAL)) == 1


def test_backup_now_without_htmx_redirects_with_a_message(backup_app):
    client, backup_dir, _stopped = backup_app
    authenticated_admin(client)

    response = client.post("/system/backup", follow_redirects=False)

    assert response.status_code == 303
    assert "/admin?msg=" in response.headers["location"]
    assert len(list(backup_dir.iterdir())) == 2


def test_a_failed_backup_shows_an_error_alert(broken_backup_app):
    client = broken_backup_app
    authenticated_admin(client)

    response = client.post(
        "/system/backup",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "No database file" in response.text
    assert len(audit_entries(client, AuditActions.BACKUP_MANUAL)) == 0


def test_settings_page_lists_the_recent_backups(backup_app):
    client, _backup_dir, _stopped = backup_app
    authenticated_admin(client)

    page = client.get("/admin")

    assert page.status_code == 200
    assert "school_finance" in page.text
    assert "Backup now" in page.text
    assert "Keeping the newest 30 backups" in page.text


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def test_admin_can_shut_down_the_app(backup_app):
    client, _backup_dir, stopped = backup_app
    authenticated_admin(client)

    response = client.post("/system/shutdown")

    assert response.status_code == 200
    assert "shutting down" in response.text.lower()
    assert stopped == [True]
    (entry,) = audit_entries(client, AuditActions.SHUTDOWN)
    assert "Head Teacher" in entry.summary


def test_shutdown_is_disabled_when_flag_set(backup_app, monkeypatch):
    from app.config import settings

    client, _backup_dir, stopped = backup_app
    authenticated_admin(client)
    monkeypatch.setattr(settings, "DISABLE_SHUTDOWN", True)

    response = client.post("/system/shutdown")

    assert response.status_code == 403
    assert "disabled" in response.text.lower()
    assert stopped == []

    page = client.get("/admin")
    assert "Shut down the app" not in page.text

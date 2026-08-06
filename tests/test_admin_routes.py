"""Admin routes end-to-end: settings page and staff-account management.

Route-level smoke tests of the thin adapters + templates. Business rules
(username uniqueness, last-admin protection, self-disable, audit content) live
in ``test_admin_service.py``. Creating users, disabling, re-enabling, and
resetting passwords are Admin-only and asserted here.
"""

import json
from typing import cast

from fastapi import FastAPI

from app.audit.service import AuditActions
from app.models import AuditLogEntry, User, UserRoles

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login,
    login_finance,
    setup_admin,
)


def _db(client):
    return cast(FastAPI, client.app).state.db


def users(client) -> list[User]:
    with _db(client).session() as session:
        return session.query(User).order_by(User.id).all()


def audit_entries(client, action):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def create_user(client, name="Jane Cashier", username="jane",
                password="temporary password", role="finance", **overrides):
    data = {
        "name": name,
        "username": username,
        "password": password,
        "role": role,
        **overrides,
    }
    return client.post(
        "/admin/users",
        data=data,
        headers={"HX-Request": "true"},
    )


# ---------------------------------------------------------------------------
# Login & role gating
# ---------------------------------------------------------------------------


def test_settings_page_requires_login(client):
    setup_admin(client)

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_settings_page_requires_admin(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/admin")
    assert response.status_code == 403


def test_user_management_requires_admin(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = create_user(client)
    assert response.status_code == 403

    (the_admin,) = [u for u in users(client) if u.role == UserRoles.ADMIN]
    disable = client.post(
        f"/admin/users/{the_admin.id}/disable",
        headers={"HX-Request": "true"},
    )
    assert disable.status_code == 403

    enable = client.post(
        f"/admin/users/{the_admin.id}/enable",
        headers={"HX-Request": "true"},
    )
    assert enable.status_code == 403

    reset = client.post(
        f"/admin/users/{the_admin.id}/password",
        data={"password": "new password"},
        headers={"HX-Request": "true"},
    )
    assert reset.status_code == 403


# ---------------------------------------------------------------------------
# Creating users
# ---------------------------------------------------------------------------


def test_admin_can_create_a_user(client):
    authenticated_admin(client)

    response = create_user(client)

    assert response.status_code == 200
    assert "jane" in response.text
    assert "toast" in response.headers["HX-Trigger"]
    (created,) = users(client)[1:]
    assert created.username == "jane"
    assert created.role == UserRoles.FINANCE
    assert created.name == "Jane Cashier"
    assert created.password_hash != "temporary password"
    assert len(audit_entries(client, AuditActions.USER_CREATE)) == 1


def test_admin_can_create_an_admin_user(client):
    authenticated_admin(client)

    response = create_user(client, name="Deputy", username="deputy", role="admin")

    assert response.status_code == 200
    (created,) = users(client)[1:]
    assert created.role == UserRoles.ADMIN


def test_creating_a_user_requires_all_fields(client):
    authenticated_admin(client)

    response = create_user(client, username="", name="")

    assert response.status_code == 200
    assert "required" in response.text.lower()
    assert len(users(client)) == 1
    assert audit_entries(client, AuditActions.USER_CREATE) == []


def test_a_duplicate_username_shows_an_error(client):
    authenticated_admin(client)
    create_user(client)

    response = create_user(client, name="Someone Else", username="jane")

    assert response.status_code == 200
    assert "already exists" in response.text
    assert len(users(client)) == 2
    assert len(audit_entries(client, AuditActions.USER_CREATE)) == 1


def test_creating_without_htmx_redirects_with_a_message(client):
    authenticated_admin(client)

    response = client.post(
        "/admin/users",
        data={
            "name": "Jane Cashier",
            "username": "jane",
            "password": "temporary password",
            "role": "finance",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/admin?msg=" in response.headers["location"]
    assert len(users(client)) == 2


# ---------------------------------------------------------------------------
# Disabling & enabling
# ---------------------------------------------------------------------------


def test_admin_can_disable_a_user(client):
    authenticated_admin(client)
    create_user(client)

    response = client.post(
        "/admin/users/2/disable",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "toast" in response.headers["HX-Trigger"]
    disabled = users(client)[1]
    assert disabled.is_active is False
    assert len(audit_entries(client, AuditActions.USER_DISABLE)) == 1


def test_admin_cannot_disable_their_own_account(client):
    authenticated_admin(client)

    response = client.post(
        "/admin/users/1/disable",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "your own account" in response.text
    assert users(client)[0].is_active is True
    assert audit_entries(client, AuditActions.USER_DISABLE) == []


def test_admin_can_enable_a_disabled_user(client):
    authenticated_admin(client)
    create_user(client)
    client.post("/admin/users/2/disable", headers={"HX-Request": "true"})

    response = client.post(
        "/admin/users/2/enable",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert users(client)[1].is_active is True
    assert len(audit_entries(client, AuditActions.USER_ENABLE)) == 1


def test_a_disabled_user_cannot_log_in(client):
    authenticated_admin(client)
    create_user(client)
    client.post("/admin/users/2/disable", headers={"HX-Request": "true"})

    client.post("/logout", follow_redirects=False)
    response = client.post(
        "/login",
        data={"username": "jane", "password": "temporary password"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid username or password" in response.text


# ---------------------------------------------------------------------------
# Resetting passwords
# ---------------------------------------------------------------------------


def test_admin_can_reset_a_password(client):
    authenticated_admin(client)
    create_user(client)

    response = client.post(
        "/admin/users/2/password",
        data={"password": "brand new password"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "toast" in response.headers["HX-Trigger"]
    assert len(audit_entries(client, AuditActions.USER_PASSWORD_RESET)) == 1

    client.post("/logout", follow_redirects=False)
    login(client, username="jane", password="brand new password")
    page = client.get("/expenses")
    assert page.status_code == 200


def test_reset_password_requires_a_value(client):
    authenticated_admin(client)
    create_user(client)

    response = client.post(
        "/admin/users/2/password",
        data={"password": "  "},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "password is required" in response.text.lower()
    assert audit_entries(client, AuditActions.USER_PASSWORD_RESET) == []


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------


def test_settings_page_lists_users_and_roles(client):
    authenticated_admin(client)
    create_user(client, name="Deputy Head", username="deputy", role="admin")

    page = client.get("/admin")

    assert page.status_code == 200
    assert "Staff accounts" in page.text
    assert "Deputy Head" in page.text
    assert "jane" in page.text
    assert "Finance officer" in page.text
    assert "Database backups" in page.text
    assert "Shut down" in page.text

"""Audit routes end-to-end: admin browse, role gate, filters, append-only.

Route-level smoke tests of the thin adapter + template. Business rules (recent-first
ordering, filtering, pagination) live in ``test_audit_service.py``.
"""

from app.main import create_app
from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login,
    login_finance,
    setup_admin,
)


def test_audit_page_requires_login(client):
    setup_admin(client)

    response = client.get("/audit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_finance_officer_cannot_browse_the_audit_log(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/audit", follow_redirects=False)
    assert response.status_code == 403


def test_admin_can_browse_the_audit_log(client):
    authenticated_admin(client)
    client.post("/logout", follow_redirects=False)
    login(client)

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Audit log" in response.text
    assert "logged in" in response.text
    assert "Created the first Admin account" in response.text


def test_audit_page_accepts_an_action_filter(client):
    authenticated_admin(client)

    response = client.get("/audit?action=login")
    assert response.status_code == 200
    assert "logged in" in response.text


def test_audit_page_accepts_a_page_number(client):
    authenticated_admin(client)

    response = client.get("/audit?page=1")
    assert response.status_code == 200
    assert "Audit log" in response.text


def test_admin_sees_an_audit_log_nav_link(client):
    authenticated_admin(client)

    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/audit"' in response.text


def test_no_ui_path_edits_or_deletes_audit_entries(client):
    authenticated_admin(client)

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Edit" not in response.text
    assert "Delete" not in response.text

    assert client.post("/audit", data={}).status_code == 405
    assert client.request("DELETE", "/audit").status_code == 405
    assert client.patch("/audit").status_code == 405

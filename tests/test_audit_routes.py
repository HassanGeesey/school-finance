"""Audit routes end-to-end: admin browse, role gate, filters, append-only.

Route-level smoke tests of the thin adapter + template. Business rules (recent-first
ordering, filtering, pagination) live in ``test_audit_service.py``.
"""

from typing import cast

from fastapi import FastAPI

from app.auth.service import hash_password
from app.models import School, User, UserRoles
from tests.helpers import (
    PASSWORD,
    add_finance_user,
    authenticated_admin,
    login,
    login_as,
    login_finance,
    seed_second_campus,
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


def test_superadmin_can_browse_the_audit_log(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    response = client.get("/audit")

    assert response.status_code == 200
    assert "Audit log" in response.text


def test_an_owner_cannot_browse_the_audit_log(client):
    authenticated_admin(client)
    with cast(FastAPI, client.app).state.db.session() as session:
        school = session.query(School).one()
        owner = User(
            name="Owner",
            username="owner",
            password_hash=hash_password("long enough password"),
            role=UserRoles.OWNER,
            school_id=school.id,
        )
        session.add(owner)
        session.commit()
    login_as(client, "owner")

    response = client.get("/audit", follow_redirects=False)
    assert response.status_code == 403


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


def test_campus_admin_browses_only_their_own_campus_entries(client):
    authenticated_admin(client)
    campus_b_id, _super = seed_second_campus(client)

    response = client.post(
        "/classes", data={"name": "Grade A", "status": "active"}, follow_redirects=False
    )
    assert response.status_code == 303
    login_as(client, "admin_b")
    response = client.post(
        "/classes", data={"name": "Grade B", "status": "active"}, follow_redirects=False
    )
    assert response.status_code == 303

    login_as(client, "admin", password=PASSWORD)
    page = client.get("/audit")
    assert page.status_code == 200
    assert "Grade A" in page.text
    assert "Grade B" not in page.text


def test_superadmin_browses_every_campus_and_school_level_entries(client):
    authenticated_admin(client)
    _campus_b_id, _super = seed_second_campus(client)
    client.post(
        "/classes", data={"name": "Grade A", "status": "active"}, follow_redirects=False
    )
    login_as(client, "admin_b")
    client.post(
        "/classes", data={"name": "Grade B", "status": "active"}, follow_redirects=False
    )

    login_as(client, "super")
    page = client.get("/audit")
    assert page.status_code == 200
    assert "Grade A" in page.text
    assert "Grade B" in page.text
    assert "Created the first Admin account" in page.text


def test_no_ui_path_edits_or_deletes_audit_entries(client):
    authenticated_admin(client)

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Edit" not in response.text
    assert "Delete" not in response.text

    assert client.post("/audit", data={}).status_code == 405
    assert client.request("DELETE", "/audit").status_code == 405
    assert client.patch("/audit").status_code == 405

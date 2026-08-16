"""Profile routes end-to-end: the settings editor, logo upload/removal, and the
setup-wizard school name.

Route-level smoke tests of the thin adapters + templates. Business rules live in
``test_profile_service.py``. These tests build the app with a temp logo
directory so uploads never touch the real data folder.
"""

from __future__ import annotations

from typing import cast
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audit.service import AuditActions
from app.main import create_app
from app.models import AuditLogEntry, Campus

from tests.helpers import (
    SCHOOL_NAME,
    PASSWORD,
    add_finance_user,
    authenticated_admin,
    login_as,
    login_finance,
    seed_second_campus,
    setup_admin,
)

PNG_LOGO = b"\x89PNG\r\n\x1a\n" + b"logo-payload"


@pytest.fixture()
def profile_app(tmp_path):
    app = create_app(database_url="sqlite://", logo_dir=tmp_path)
    with TestClient(app) as client:
        yield client, tmp_path


def _db(client) -> object:
    return cast(FastAPI, client.app).state.db


def audit_entries(client, action: str) -> list[AuditLogEntry]:
    with cast(FastAPI, client.app).state.db.session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def profile(client) -> Campus:
    """The implicit Campus the offline setup bootstrapped (its profile)."""
    with cast(FastAPI, client.app).state.db.session() as session:
        return session.query(Campus).one()


def campus_by_name(client, name: str) -> Campus:
    with cast(FastAPI, client.app).state.db.session() as session:
        return session.query(Campus).filter(Campus.name == name).one()


# ---------------------------------------------------------------------------
# Setup wizard — the school name
# ---------------------------------------------------------------------------


def test_setup_requires_a_school_name(client):
    response = client.post(
        "/setup",
        data={"name": "Head Teacher", "username": "admin", "password": "long enough"},
    )

    assert response.status_code == 400
    assert "school name is required" in response.text.lower()


def test_setup_names_the_implicit_campus(client):
    response = client.post(
        "/setup",
        data={
            "school_name": SCHOOL_NAME,
            "name": "Head Teacher",
            "username": "admin",
            "password": "long enough",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert profile(client).name == SCHOOL_NAME


# ---------------------------------------------------------------------------
# Role gating
# ---------------------------------------------------------------------------


def test_profile_editing_requires_admin(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post("/profile", data={"school_name": "X"})
    assert response.status_code == 403

    response = client.post("/profile/logo", files={"logo": ("logo.png", b"x", "image/png")})
    assert response.status_code == 403

    response = client.post("/profile/logo/remove")
    assert response.status_code == 403


def test_settings_page_shows_the_school_profile_card(client):
    authenticated_admin(client)

    page = client.get("/admin")

    assert page.status_code == 200
    assert "School profile" in page.text
    assert SCHOOL_NAME in page.text


# ---------------------------------------------------------------------------
# Editing the profile
# ---------------------------------------------------------------------------


def test_admin_can_update_the_profile(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile",
        data={
            "school_name": "Sunrise Primary School",
            "address": "123 Main St",
            "phone": "555-1234",
            "email": "info@school.example",
            "website": "https://school.example",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "toast" in response.headers["HX-Trigger"]
    stored = profile(client)
    assert stored.name == "Sunrise Primary School"
    assert stored.address == "123 Main St"
    assert stored.website == "https://school.example"
    entries = audit_entries(client, AuditActions.PROFILE_UPDATE)
    assert "Sunrise Primary School" in entries[-1].summary


def test_updating_with_a_blank_school_name_is_refused(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)
    before = len(audit_entries(client, AuditActions.PROFILE_UPDATE))

    response = client.post(
        "/profile",
        data={"school_name": "  "},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "school name is required" in response.text.lower()
    assert len(audit_entries(client, AuditActions.PROFILE_UPDATE)) == before


def test_updating_without_htmx_redirects_with_a_message(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile",
        data={"school_name": "Sunrise Primary School"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/admin?msg=" in response.headers["location"]


def test_contact_fields_accept_any_text(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile",
        data={
            "school_name": "Sunrise Primary School",
            "email": "not an email address",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert profile(client).email == "not an email address"


# ---------------------------------------------------------------------------
# Logo upload & removal
# ---------------------------------------------------------------------------


def test_admin_can_upload_a_logo(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile/logo",
        files={"logo": ("school-logo.png", PNG_LOGO, "image/png")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "toast" in response.headers["HX-Trigger"]
    assert profile(client).logo_filename == "logo.png"
    assert (tmp / "logo.png").read_bytes() == PNG_LOGO
    assert len(audit_entries(client, AuditActions.PROFILE_LOGO_UPLOAD)) == 1


def test_uploading_a_non_image_logo_is_refused(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile/logo",
        files={"logo": ("evil.exe", b"x", "application/octet-stream")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "must be an image" in response.text
    assert profile(client).logo_filename is None
    assert len(audit_entries(client, AuditActions.PROFILE_LOGO_UPLOAD)) == 0


def test_uploading_a_renamed_file_is_refused(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)

    response = client.post(
        "/profile/logo",
        files={"logo": ("report.png", b"plain text, not a png", "image/png")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "must be an image" in response.text
    assert profile(client).logo_filename is None
    assert not (tmp / "logo.png").exists()
    assert len(audit_entries(client, AuditActions.PROFILE_LOGO_UPLOAD)) == 0


def test_the_logo_is_served_only_by_its_stored_name(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)
    client.post(
        "/profile/logo",
        files={"logo": ("logo.png", PNG_LOGO, "image/png")},
        headers={"HX-Request": "true"},
    )

    served = client.get("/logos/logo.png")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == PNG_LOGO

    missing = client.get("/logos/other.png")
    assert missing.status_code == 404


def test_admin_can_remove_the_logo(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)
    client.post(
        "/profile/logo",
        files={"logo": ("logo.png", PNG_LOGO, "image/png")},
        headers={"HX-Request": "true"},
    )

    response = client.post(
        "/profile/logo/remove",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert profile(client).logo_filename is None
    assert not (tmp / "logo.png").exists()
    assert len(audit_entries(client, AuditActions.PROFILE_LOGO_REMOVE)) == 1


# ---------------------------------------------------------------------------
# App shell branding
# ---------------------------------------------------------------------------


def test_app_shell_shows_the_school_name_after_setup(client):
    authenticated_admin(client)

    page = client.get("/")

    assert page.status_code == 200
    assert SCHOOL_NAME in page.text
    assert f"<title>Dashboard — {SCHOOL_NAME}</title>" in page.text


def test_login_page_keeps_the_product_name(client):
    setup_admin(client)

    page = client.get("/login")

    assert page.status_code == 200
    assert "School Finance" in page.text


# ---------------------------------------------------------------------------
# Per-Campus isolation (multi-school ticket 07)
# ---------------------------------------------------------------------------


def test_campus_admins_edit_isolated_identities(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)
    seed_second_campus(client)

    client.post(
        "/profile",
        data={"school_name": "Campus A Academy", "phone": "111-1111"},
        headers={"HX-Request": "true"},
    )
    login_as(client, "admin_b")
    client.post(
        "/profile",
        data={"school_name": "Campus B Academy", "phone": "222-2222"},
        headers={"HX-Request": "true"},
    )

    campus_a = campus_by_name(client, "Campus A Academy")
    campus_b = campus_by_name(client, "Campus B Academy")
    assert campus_a.phone == "111-1111"
    assert campus_b.phone == "222-2222"


def test_the_app_shell_shows_the_acting_campus_identity(profile_app):
    client, _tmp = profile_app
    authenticated_admin(client)
    seed_second_campus(client)
    client.post(
        "/profile",
        data={"school_name": "Campus A Academy"},
        headers={"HX-Request": "true"},
    )
    login_as(client, "admin_b")
    client.post(
        "/profile",
        data={"school_name": "Campus B Academy"},
        headers={"HX-Request": "true"},
    )

    login_as(client, "admin", password=PASSWORD)
    page = client.get("/")
    assert page.status_code == 200
    assert "Campus A Academy" in page.text
    assert "Campus B Academy" not in page.text


def test_a_campus_admin_cannot_edit_the_other_campus_logo(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)
    seed_second_campus(client)
    client.post(
        "/profile/logo",
        files={"logo": ("logo.png", PNG_LOGO, "image/png")},
        headers={"HX-Request": "true"},
    )

    campus_a = campus_by_name(client, "Sunrise Primary School")
    campus_b = campus_by_name(client, "Campus B")
    assert campus_a.logo_filename == "logo.png"
    assert campus_b.logo_filename is None


# ---------------------------------------------------------------------------
# Printed documents carry the school identity (ticket 16)
# ---------------------------------------------------------------------------


def add_fee_template(client, name="Tuition", amount="50.00"):
    response = client.post(
        "/fees/templates",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with cast(FastAPI, client.app).state.db.session() as session:
        from app.models import FeeTemplate

        return session.query(FeeTemplate).order_by(FeeTemplate.id.desc()).first().id


def create_class(client, name="Grade 1", template_id=None):
    data = {"name": name, "status": "active"}
    if template_id is not None:
        data["default_template_id"] = str(template_id)
    response = client.post(
        "/classes",
        data=data,
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def add_student(client, class_id):
    response = client.post(
        f"/classes/{class_id}/students",
        data={"first_name": "Ada", "last_name": "Lovelace"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def make_billed_student(client):
    template_id = add_fee_template(client)
    class_id = create_class(client, template_id=template_id)
    add_student(client, class_id)
    with cast(FastAPI, client.app).state.db.session() as session:
        from app.models import Student

        return session.query(Student).one().id


def record_payment(client, student_id):
    response = client.post(
        "/payments/record",
        data={
            "student_id": str(student_id),
            "amount": "30.00",
            "method": "cash",
            "paid_on": "2026-08-06",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def set_contact(client):
    response = client.post(
        "/profile",
        data={
            "school_name": SCHOOL_NAME,
            "address": "123 Main St",
            "phone": "555-1234",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200


def test_the_printed_receipt_shows_the_school_identity(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)
    set_contact(client)
    client.post(
        "/profile/logo",
        files={"logo": ("logo.png", PNG_LOGO, "image/png")},
        headers={"HX-Request": "true"},
    )
    sid = make_billed_student(client)
    location = record_payment(client, sid)

    page = client.get(location)

    assert page.status_code == 200
    assert SCHOOL_NAME in page.text
    assert 'src="/logos/logo.png"' in page.text
    assert "123 Main St" in page.text
    assert "555-1234" in page.text


def test_the_printed_statement_shows_the_school_identity(client):
    authenticated_admin(client)
    set_contact(client)
    sid = make_billed_student(client)

    page = client.get(f"/students/{sid}/account")

    assert page.status_code == 200
    assert SCHOOL_NAME in page.text
    assert "Student statement" in page.text
    assert "123 Main St" in page.text
    assert "555-1234" in page.text
    assert "print-only" in page.text


def test_the_contact_block_prints_only_non_empty_fields(client):
    authenticated_admin(client)
    set_contact(client)
    sid = make_billed_student(client)

    page = client.get(f"/students/{sid}/account")

    assert page.status_code == 200
    assert "info@school.example" not in page.text
    assert "school.example" not in page.text


def test_reprinting_a_receipt_shows_the_current_profile(profile_app):
    client, tmp = profile_app
    authenticated_admin(client)
    sid = make_billed_student(client)
    location = record_payment(client, sid)

    before = client.get(location)
    assert SCHOOL_NAME in before.text

    response = client.post(
        "/profile",
        data={"school_name": "New Name Academy", "phone": "555-9999"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    after = client.get(location)
    assert "New Name Academy" in after.text
    assert "555-9999" in after.text
    assert SCHOOL_NAME not in after.text

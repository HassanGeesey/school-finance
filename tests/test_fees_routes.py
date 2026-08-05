"""Fee generation routes end-to-end: the billing page, preview, and generation.

Route-level smoke tests of the thin adapters + templates. Business rules
(validation, duplicate safety, snapshotting, audit content) live in
``test_fees_service.py``.
"""

from typing import cast
from urllib.parse import urlparse

from fastapi import FastAPI

from app.audit.service import AuditActions
from app.models import AuditLogEntry

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def create_class(client, name="Grade 1", status="active"):
    response = client.post(
        "/classes",
        data={"name": name, "status": status},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def add_fee_item(client, class_id, name="Tuition", amount="50.00"):
    response = client.post(
        f"/classes/{class_id}/fee-items",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )
    assert response.status_code == 303


def add_student(client, class_id, first_name="Ada", last_name="Lovelace"):
    response = client.post(
        f"/classes/{class_id}/students",
        data={"first_name": first_name, "last_name": last_name},
        follow_redirects=False,
    )
    assert response.status_code == 303


def audit_entries(client, action=AuditActions.FEE_GENERATE):
    with cast(FastAPI, client.app).state.db.session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def test_fees_page_requires_login(client):
    setup_admin(client)

    response = client.get("/fees", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_finance_officer_can_open_the_fees_page(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/fees")
    assert response.status_code == 200
    assert "Generate monthly fees" in response.text
    assert "All classes" in response.text


def test_fees_page_lists_active_classes_with_their_monthly_fee(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id, amount="62.50")

    response = client.get("/fees")
    assert response.status_code == 200
    assert "Grade 1" in response.text
    assert "$62.50/month" in response.text


def test_completed_classes_are_not_offered(client):
    authenticated_admin(client)
    class_id = create_class(client, name="Grade 8", status="completed")
    add_fee_item(client, class_id)

    response = client.get("/fees")
    assert response.status_code == 200
    assert "Grade 8" not in response.text


def test_fees_page_shows_an_empty_state_without_active_classes(client):
    authenticated_admin(client)
    create_class(client, name="Grade 8", status="completed")

    response = client.get("/fees")
    assert response.status_code == 200
    assert "No active classes" in response.text
    assert "Generate monthly fees" not in response.text


def test_preview_shows_the_breakdown_for_confirm(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)

    response = client.post(
        "/fees/preview",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Confirm fee generation" in response.text
    assert "March 2026" in response.text
    assert "Will bill" in response.text
    assert "$50.00" in response.text
    assert "1 student will be billed" in response.text


def test_preview_for_all_classes_lists_each_class(client):
    authenticated_admin(client)
    class_a = create_class(client, name="Grade 1")
    add_fee_item(client, class_a)
    add_student(client, class_a)
    class_b = create_class(client, name="Grade 2")
    add_fee_item(client, class_b, amount="75.00")
    add_student(client, class_b, first_name="Grace", last_name="Hopper")

    response = client.post(
        "/fees/preview",
        data={"class_id": "", "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Grade 1" in response.text
    assert "Grade 2" in response.text
    assert "$125.00" in response.text


def test_preview_of_an_already_generated_class_is_refused(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)

    client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    response = client.post(
        "/fees/preview",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "already been generated" in response.text
    assert "Generate" not in response.text


def test_preview_rejects_an_invalid_period(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)

    response = client.post(
        "/fees/preview",
        data={"class_id": str(class_id), "month": "13", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "between 1 and 12" in response.text


def test_generate_requires_login(client):
    setup_admin(client)

    response = client.post(
        "/fees/generate",
        data={"class_id": "1", "month": "3", "year": "2026"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_finance_officer_can_generate_fees(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Grade 1 — March 2026" in response.text
    assert "1 charge(s)" in response.text
    assert "$50.00" in response.text
    assert len(audit_entries(client)) == 1


def test_admin_can_generate_fees_for_all_classes(client):
    authenticated_admin(client)
    class_a = create_class(client, name="Grade 1")
    add_fee_item(client, class_a)
    add_student(client, class_a)
    class_b = create_class(client, name="Grade 2")
    add_fee_item(client, class_b, amount="75.00")
    add_student(client, class_b, first_name="Grace", last_name="Hopper")

    response = client.post(
        "/fees/generate",
        data={"class_id": "", "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Generated March 2026 fees" in response.text
    assert "2 charge(s)" in response.text
    assert "$125.00" in response.text


def test_generating_twice_for_the_same_class_is_refused(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)

    first = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert first.status_code == 200

    second = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert second.status_code == 200
    assert "already been generated" in second.text
    assert len(audit_entries(client)) == 1


def test_generating_all_skips_classes_that_were_already_billed(client):
    authenticated_admin(client)
    class_a = create_class(client, name="Grade 1")
    add_fee_item(client, class_a)
    add_student(client, class_a)
    class_b = create_class(client, name="Grade 2")
    add_fee_item(client, class_b, amount="75.00")
    add_student(client, class_b, first_name="Grace", last_name="Hopper")

    client.post(
        "/fees/generate",
        data={"class_id": str(class_a), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    response = client.post(
        "/fees/generate",
        data={"class_id": "", "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "1 charge(s)" in response.text
    assert "1 class(es) skipped" in response.text


def test_generating_a_completed_class_is_refused(client):
    authenticated_admin(client)
    class_id = create_class(client, name="Grade 8", status="completed")
    add_fee_item(client, class_id)

    response = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "not active" in response.text
    assert len(audit_entries(client)) == 0


def test_generation_appears_in_the_audit_log(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)

    client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        headers={"HX-Request": "true"},
    )

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Monthly fees generated" in response.text
    assert "Grade 1" in response.text
    assert "$50.00" in response.text


def test_non_htmx_generate_redirects_with_a_message(client):
    authenticated_admin(client)
    class_id = create_class(client)
    add_fee_item(client, class_id)
    add_student(client, class_id)

    response = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": "3", "year": "2026"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/fees?msg=")

    page = client.get(response.headers["location"])
    assert "Grade 1 — March 2026" in page.text

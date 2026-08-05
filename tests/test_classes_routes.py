"""Class routes end-to-end: admin editing, finance read-only, audit trail.

Route-level smoke tests of the thin adapters + templates. Business rules
(validation, duplicate names, status transitions, audit content) live in
``test_classes_service.py``.
"""

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def create_class(client, name="Grade 1", status="active"):
    return client.post(
        "/classes",
        data={"name": name, "status": status},
        follow_redirects=False,
    )


def add_fee_item(client, class_id, name="Tuition", amount="50.00"):
    return client.post(
        f"/classes/{class_id}/fee-items",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )


def test_classes_index_requires_login(client):
    setup_admin(client)

    response = client.get("/classes", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_finance_officer_can_view_the_class_index(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/classes")
    assert response.status_code == 200
    assert "Classes" in response.text


def test_finance_officer_cannot_open_the_new_class_form(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/classes/new", follow_redirects=False)
    assert response.status_code == 403


def test_finance_officer_cannot_create_a_class(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = create_class(client)
    assert response.status_code == 403


def test_admin_can_create_a_class(client):
    authenticated_admin(client)

    response = create_class(client)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/")

    index = client.get("/classes")
    assert index.status_code == 200
    assert "Grade 1" in index.text


def test_class_creation_requires_a_name(client):
    authenticated_admin(client)

    response = create_class(client, name="   ")
    assert response.status_code == 400
    assert "Class name is required" in response.text


def test_admin_can_create_a_completed_class_and_it_is_marked(client):
    authenticated_admin(client)

    response = create_class(client, name="Grade 8", status="completed")
    assert response.status_code == 303

    index = client.get("/classes")
    assert index.status_code == 200
    assert "Grade 8" in index.text
    assert "Completed" in index.text


def test_class_creation_is_visible_in_the_audit_log(client):
    authenticated_admin(client)

    create_class(client)

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Class created" in response.text
    assert "Grade 1" in response.text


def test_class_detail_requires_login(client):
    setup_admin(client)

    response = client.get("/classes/1", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_missing_class_detail_returns_404(client):
    authenticated_admin(client)

    response = client.get("/classes/999")
    assert response.status_code == 404


def test_finance_officer_can_view_a_class_detail(client):
    authenticated_admin(client)
    create_class(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/classes/1")
    assert response.status_code == 200
    assert "Grade 1" in response.text


def test_finance_officer_cannot_update_a_class(client):
    authenticated_admin(client)
    create_class(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/classes/1/edit",
        data={"name": "Hijacked", "status": "active"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_admin_can_rename_and_change_status(client):
    authenticated_admin(client)
    create_class(client)

    response = client.post(
        "/classes/1/edit",
        data={"name": "Grade One", "status": "inactive"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert detail.status_code == 200
    assert "Grade One" in detail.text
    assert "Inactive" in detail.text


def test_class_update_is_visible_in_the_audit_log(client):
    authenticated_admin(client)
    create_class(client)

    client.post(
        "/classes/1/edit",
        data={"name": "Grade One", "status": "inactive"},
        follow_redirects=False,
    )

    response = client.get("/audit")
    assert "Class renamed" in response.text
    assert "Class status changed" in response.text


def test_finance_officer_cannot_add_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)
    add_finance_user(client)
    login_finance(client)

    response = add_fee_item(client, 1)
    assert response.status_code == 403


def test_admin_can_add_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)

    response = add_fee_item(client, 1)
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Tuition" in detail.text
    assert "$50.00" in detail.text


def test_fee_item_addition_requires_a_positive_amount(client):
    authenticated_admin(client)
    create_class(client)

    response = add_fee_item(client, 1, amount="0")
    assert response.status_code == 400
    assert "greater than zero" in response.text


def test_fee_item_addition_rejects_duplicates(client):
    authenticated_admin(client)
    create_class(client)
    add_fee_item(client, 1)

    response = add_fee_item(client, 1)
    assert response.status_code == 400
    assert "already has a fee item" in response.text


def test_finance_officer_cannot_edit_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)
    add_fee_item(client, 1)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/classes/1/fee-items/1/edit",
        data={"name": "Tuition", "amount": "99.00"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_admin_can_edit_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)
    add_fee_item(client, 1)

    response = client.post(
        "/classes/1/fee-items/1/edit",
        data={"name": "Tuition Fee", "amount": "55.50"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Tuition Fee" in detail.text
    assert "$55.50" in detail.text


def test_editing_a_fee_item_from_another_class_is_rejected(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")
    add_fee_item(client, 2)

    response = client.post(
        "/classes/1/fee-items/1/edit",
        data={"name": "Hijacked", "amount": "99.00"},
        follow_redirects=False,
    )
    assert response.status_code == 404

    detail = client.get("/classes/2")
    assert "Tuition" in detail.text
    assert "Hijacked" not in detail.text


def test_removing_a_fee_item_from_another_class_is_rejected(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")
    add_fee_item(client, 2)

    response = client.post("/classes/1/fee-items/1/delete", follow_redirects=False)
    assert response.status_code == 404

    detail = client.get("/classes/2")
    assert "Tuition" in detail.text


def test_finance_officer_cannot_remove_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)
    add_fee_item(client, 1)
    add_finance_user(client)
    login_finance(client)

    response = client.post(
        "/classes/1/fee-items/1/delete", follow_redirects=False
    )
    assert response.status_code == 403


def test_admin_can_remove_a_fee_item(client):
    authenticated_admin(client)
    create_class(client)
    add_fee_item(client, 1)

    response = client.post("/classes/1/fee-items/1/delete", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "No fee items yet" in detail.text

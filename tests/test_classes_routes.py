"""Class routes: listing and editing classes and their default fee template.

Thin adapters over :class:`app.classes.service.ClassService`. Viewing is open to
any logged-in user; every mutation is Admin-only and audited. The default
template picker draws from the Admin-managed fee templates. Service rules live in
``test_classes_service.py``.
"""

import pytest

from app.models import AuditLogEntry, Class


def authenticated_mini_client(mini_client):
    from tests.helpers import authenticated_admin

    authenticated_admin(mini_client)
    return mini_client


def login_finance_client(mini_client):
    from tests.helpers import add_finance_user, login_finance

    add_finance_user(mini_client)
    login_finance(mini_client)
    return mini_client


def create_template(client, name="Standard", amount="100.00"):
    return client.app.state.fees.create_template(user=None, name=name, amount=amount)


def create_class(client, name="Grade 1", default_template_id=""):
    data = {"name": name, "status": "active", "default_template_id": default_template_id}
    return client.post("/classes", data=data, follow_redirects=False)


# ---------------------------------------------------------------------------
# Viewing
# ---------------------------------------------------------------------------


def test_classes_index_requires_login(mini_client):
    response = mini_client.get("/classes", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_classes_index_lists_classes(mini_client):
    client = authenticated_mini_client(mini_client)
    create_class(client, name="Grade 1")

    response = client.get("/classes")

    assert response.status_code == 200
    assert "Grade 1" in response.text


def test_classes_index_is_open_to_finance(mini_client):
    client = login_finance_client(mini_client)

    assert client.get("/classes").status_code == 200


# ---------------------------------------------------------------------------
# New class form
# ---------------------------------------------------------------------------


def test_new_class_form_is_admin_only(mini_client):
    client = login_finance_client(mini_client)

    assert client.get("/classes/new").status_code == 403


def test_new_class_form_lists_active_template_options(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Standard", amount="50.00")

    response = client.get("/classes/new")

    assert response.status_code == 200
    assert "Default fee template" in response.text
    assert "Standard" in response.text


def test_new_class_form_excludes_archived_templates(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, name="Old")
    client.app.state.fees.archive_template(user=None, template_id=template.id)

    response = client.get("/classes/new")

    assert response.status_code == 200
    assert "Old" not in response.text


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_class_redirects_to_the_detail_page(mini_client):
    client = authenticated_mini_client(mini_client)

    response = create_class(client, name="Grade 1")

    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/")


def test_create_class_with_a_default_template(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, amount="75.00")

    response = create_class(client, name="Grade 1", default_template_id=str(template.id))

    assert response.status_code == 303
    with client.app.state.db.session() as session:
        row = session.query(Class).one()
        assert row.default_template_id == template.id


def test_create_class_requires_admin(mini_client):
    client = login_finance_client(mini_client)

    response = create_class(client, name="Grade 1")

    assert response.status_code == 403


def test_create_class_rejects_an_invalid_template(mini_client):
    client = authenticated_mini_client(mini_client)

    response = create_class(client, name="Grade 1", default_template_id="999")

    assert response.status_code == 400
    assert "Choose a valid fee template" in response.text
    with client.app.state.db.session() as session:
        assert session.query(Class).count() == 0


def test_create_class_rejects_an_archived_template(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client)
    client.app.state.fees.archive_template(user=None, template_id=template.id)

    response = create_class(client, name="Grade 1", default_template_id=str(template.id))

    assert response.status_code == 400
    assert "Choose a valid fee template" in response.text


def test_create_class_requires_a_name(mini_client):
    client = authenticated_mini_client(mini_client)

    response = create_class(client, name="")

    assert response.status_code == 400
    assert "Class name is required" in response.text


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def test_class_detail_shows_the_default_template(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client, amount="85.00")
    class_id = int(create_class(client, "Grade 1", str(template.id)).headers["location"].split("/")[-1].split("?")[0])

    response = client.get(f"/classes/{class_id}")

    assert response.status_code == 200
    assert "Standard" in response.text
    assert "$85.00" in response.text


def test_class_detail_without_a_default_template(mini_client):
    client = authenticated_mini_client(mini_client)
    class_id = int(create_class(client, "Grade 1").headers["location"].split("/")[-1].split("?")[0])

    response = client.get(f"/classes/{class_id}")

    assert response.status_code == 200
    assert "no default template" in response.text


def test_class_detail_missing_class_404s(mini_client):
    client = authenticated_mini_client(mini_client)

    assert client.get("/classes/999").status_code == 404


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_class_sets_the_default_template(mini_client):
    client = authenticated_mini_client(mini_client)
    class_id = int(create_class(client, "Grade 1").headers["location"].split("/")[-1].split("?")[0])
    template = create_template(client, name="Standard", amount="60.00")

    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "Grade 1", "status": "active", "default_template_id": str(template.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with client.app.state.db.session() as session:
        assert session.query(Class).one().default_template_id == template.id
        entry = (
            session.query(AuditLogEntry)
            .filter_by(action="class_default_template")
            .one()
        )
        assert "Standard" in entry.summary


def test_edit_class_clears_the_default_template(mini_client):
    client = authenticated_mini_client(mini_client)
    template = create_template(client)
    class_id = int(
        create_class(client, "Grade 1", str(template.id)).headers["location"].split("/")[-1].split("?")[0]
    )

    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "Grade 1", "status": "active", "default_template_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with client.app.state.db.session() as session:
        assert session.query(Class).one().default_template_id is None
        entries = session.query(AuditLogEntry).filter_by(action="class_default_template").all()
        assert any("Cleared" in entry.summary for entry in entries)


def test_edit_class_rejects_an_invalid_template(mini_client):
    client = authenticated_mini_client(mini_client)
    class_id = int(create_class(client, "Grade 1").headers["location"].split("/")[-1].split("?")[0])

    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "Grade 1", "status": "active", "default_template_id": "999"},
    )

    assert response.status_code == 400
    assert "Choose a valid fee template" in response.text


def test_edit_class_requires_admin(mini_client):
    client = authenticated_mini_client(mini_client)
    class_id = int(create_class(client, "Grade 1").headers["location"].split("/")[-1].split("?")[0])
    login_finance_client(client)

    response = client.post(
        f"/classes/{class_id}/edit",
        data={"name": "Grade 1", "status": "active", "default_template_id": ""},
    )

    assert response.status_code == 403


def test_edit_class_missing_class_404s(mini_client):
    client = authenticated_mini_client(mini_client)

    response = client.post(
        "/classes/999/edit",
        data={"name": "Grade 1", "status": "active", "default_template_id": ""},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Two-campus scoping
# ---------------------------------------------------------------------------


def _bind_implicit_admin_and_seed_campus_b(client):
    """Bind the setup wizard's admin to the implicit Campus and create a second
    Campus with its own Admin and one class, all via the DB (ticket 03)."""
    from app.auth.service import hash_password
    from app.models import Campus, Class, School, User, UserRoles

    with client.app.state.db.session() as session:
        school = session.query(School).first()
        campus_a = session.query(Campus).first()
        admin = session.query(User).filter_by(username="admin").one()
        admin.school_id = school.id
        admin.campus_id = campus_a.id
        campus_b = Campus(school_id=school.id, name="Campus B")
        session.add(campus_b)
        session.flush()
        class_b = Class(name="Grade B", campus_id=campus_b.id)
        session.add(class_b)
        session.flush()
        session.add(
            User(
                username="admin_b",
                name="Admin B",
                password_hash=hash_password("password b"),
                role=UserRoles.ADMIN,
                school_id=school.id,
                campus_id=campus_b.id,
            )
        )
        session.commit()
        return class_b.id


def test_classes_are_scoped_to_the_acting_campus(mini_client):
    from tests.helpers import login

    client = authenticated_mini_client(mini_client)
    class_b_id = _bind_implicit_admin_and_seed_campus_b(client)
    class_a_id = int(create_class(client, name="Grade A").headers["location"].split("/")[-1].split("?")[0])

    page = client.get("/classes")
    assert "Grade A" in page.text
    assert "Grade B" not in page.text
    assert client.get(f"/classes/{class_b_id}").status_code == 404

    client.post("/logout", follow_redirects=False)
    login(client, username="admin_b", password="password b")
    page = client.get("/classes")
    assert "Grade B" in page.text
    assert "Grade A" not in page.text
    assert client.get(f"/classes/{class_a_id}").status_code == 404

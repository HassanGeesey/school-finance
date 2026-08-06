"""Student routes end-to-end: admin mutations, finance read-only, audit trail.

Route-level smoke tests of the thin adapters + templates. Business rules
(validation, archiving, CSV parsing/skip reporting, audit content) live in
``test_students_service.py``.
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


def add_student(client, class_id=1, first_name="Ada", last_name="Lovelace"):
    return client.post(
        f"/classes/{class_id}/students",
        data={"first_name": first_name, "last_name": last_name},
        follow_redirects=False,
    )


def test_search_page_requires_login(client):
    setup_admin(client)

    response = client.get("/students", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_finance_officer_can_view_the_students_search(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/students")
    assert response.status_code == 200
    assert "Students" in response.text


def test_search_finds_students_across_classes(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")
    add_student(client, class_id=1, first_name="Ada", last_name="Lovelace")
    add_student(client, class_id=2, first_name="Grace", last_name="Hopper")

    response = client.get("/students?q=hop")

    assert response.status_code == 200
    assert "Grace Hopper" in response.text
    assert "Grade 2" in response.text
    assert "Ada Lovelace" not in response.text


def test_search_page_shows_an_empty_state(client):
    authenticated_admin(client)

    response = client.get("/students?q=zzz")

    assert response.status_code == 200
    assert "No students found" in response.text


def test_class_filter_dropdown_lists_all_classes(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")

    response = client.get("/students")

    assert response.status_code == 200
    assert "All classes" in response.text
    assert 'value="1"' in response.text
    assert 'value="2"' in response.text


def test_class_filter_narrows_the_results(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")
    add_student(client, class_id=1, first_name="Ada", last_name="Lovelace")
    add_student(client, class_id=2, first_name="Grace", last_name="Hopper")

    response = client.get("/students?class_id=1")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text


def test_class_filter_combines_with_name_search(client):
    authenticated_admin(client)
    create_class(client, name="Grade 1")
    create_class(client, name="Grade 2")
    add_student(client, class_id=1, first_name="Ada", last_name="Lovelace")
    add_student(client, class_id=2, first_name="Ada", last_name="Byron")

    response = client.get("/students?class_id=2&q=ada")

    assert response.status_code == 200
    assert "Ada Byron" in response.text
    assert "Ada Lovelace" not in response.text


def test_unknown_class_filter_returns_404(client):
    authenticated_admin(client)
    create_class(client)

    assert client.get("/students?class_id=999").status_code == 404


def test_finance_officer_cannot_add_a_student(client):
    authenticated_admin(client)
    create_class(client)
    add_finance_user(client)
    login_finance(client)

    response = add_student(client)
    assert response.status_code == 403


def test_admin_can_add_a_student_and_the_class_page_lists_it(client):
    authenticated_admin(client)
    create_class(client)

    response = add_student(client)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/1?")

    detail = client.get("/classes/1")
    assert detail.status_code == 200
    assert "Ada Lovelace" in detail.text
    assert "1 student" in detail.text


def test_add_student_requires_both_names(client):
    authenticated_admin(client)
    create_class(client)

    response = add_student(client, first_name="", last_name="Lovelace")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/1?err=")

    detail = client.get(response.headers["location"])
    assert "First name is required" in detail.text


def test_add_student_is_visible_in_the_audit_log(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.get("/audit")
    assert "Student added" in response.text
    assert "Ada Lovelace" in response.text


def test_finance_officer_cannot_open_the_import_form(client):
    authenticated_admin(client)
    create_class(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/classes/1/students/import", follow_redirects=False)
    assert response.status_code == 403


def test_import_form_renders_for_admin(client):
    authenticated_admin(client)
    create_class(client)

    response = client.get("/classes/1/students/import")
    assert response.status_code == 200
    assert "CSV file" in response.text


def test_admin_can_import_students_and_sees_a_report(client):
    authenticated_admin(client)
    create_class(client)

    response = client.post(
        "/classes/1/students/import",
        files={"file": ("students.csv", b"first_name,last_name\nAda,Lovelace\nGrace,Hopper\n", "text/csv")},
    )

    assert response.status_code == 200
    assert "Import report" in response.text
    assert "2 students imported" in response.text
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" in response.text

    detail = client.get("/classes/1")
    assert "Ada Lovelace" in detail.text
    assert "Grace Hopper" in detail.text


def test_import_reports_skipped_rows(client):
    authenticated_admin(client)
    create_class(client)

    response = client.post(
        "/classes/1/students/import",
        files={"file": ("students.csv", b"Ada,Lovelace\n,Lovelace\nGrace,Hopper\n", "text/csv")},
    )

    assert response.status_code == 200
    assert "2 students imported" in response.text
    assert "1 row skipped" in response.text
    assert "Missing first name" in response.text


def test_import_of_an_empty_file_returns_an_error(client):
    authenticated_admin(client)
    create_class(client)

    response = client.post(
        "/classes/1/students/import",
        files={"file": ("students.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert "No student rows" in response.text


def test_import_is_visible_in_the_audit_log(client):
    authenticated_admin(client)
    create_class(client)
    client.post(
        "/classes/1/students/import",
        files={"file": ("students.csv", b"Ada,Lovelace\n", "text/csv")},
    )

    response = client.get("/audit")
    assert "Students imported" in response.text


def test_finance_officer_cannot_archive_a_student(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.post("/students/1/archive", follow_redirects=False)
    assert response.status_code == 403


def test_admin_can_archive_and_restore_a_student(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.post("/students/1/archive", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Inactive" in detail.text
    assert "Restore" in detail.text

    response = client.post("/students/1/restore", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Active" in detail.text


def test_archive_and_restore_are_visible_in_the_audit_log(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)
    client.post("/students/1/archive", follow_redirects=False)
    client.post("/students/1/restore", follow_redirects=False)

    response = client.get("/audit")
    assert "Student archived" in response.text
    assert "Student restored" in response.text


def test_finance_officer_cannot_edit_a_student(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/students/1/edit", follow_redirects=False)
    assert response.status_code == 403


def test_admin_can_edit_a_student_name(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.post(
        "/students/1/edit",
        data={"first_name": "Ada", "last_name": "King"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Ada King" in detail.text
    assert "Ada Lovelace" not in detail.text


def test_editing_a_student_requires_a_name(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.post(
        "/students/1/edit",
        data={"first_name": "", "last_name": "King"},
    )
    assert response.status_code == 400
    assert "First name is required" in response.text


def test_student_update_is_visible_in_the_audit_log(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    client.post(
        "/students/1/edit",
        data={"first_name": "Ada", "last_name": "King"},
        follow_redirects=False,
    )

    response = client.get("/audit")
    assert "Student updated" in response.text
    assert "Ada Lovelace" in response.text
    assert "Ada King" in response.text


def test_missing_student_returns_404(client):
    authenticated_admin(client)
    create_class(client)

    assert client.get("/students/999/edit").status_code == 404
    assert client.post("/students/999/archive", follow_redirects=False).status_code == 404
    assert client.post("/students/999/restore", follow_redirects=False).status_code == 404

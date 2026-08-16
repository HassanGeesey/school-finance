"""Student routes end-to-end: admin mutations, finance read-only, audit trail.

Route-level smoke tests of the thin adapters + templates. Business rules
(validation, archiving, CSV parsing/skip reporting, audit content, the
effective-dated amount schedule) live in ``test_students_service.py``.

Billing is derived from enrollment (there is no fee-generation step): a student
enrolled ``2026-03-01`` owes from March 2026 through the current month, which is
what makes the /students month dropdown and paid column appear.
"""

from datetime import date
from urllib.parse import urlparse

from app.fees.service import period_label

from tests.helpers import (
    add_finance_user,
    authenticated_admin,
    login_finance,
    setup_admin,
)


def create_class(client, name="Grade 1", status="active", template_id=None):
    data = {"name": name, "status": status}
    if template_id is not None:
        data["default_template_id"] = str(template_id)
    return client.post(
        "/classes",
        data=data,
        follow_redirects=False,
    )


def create_class_id(client, name="Grade 1", status="active"):
    response = create_class(client, name=name, status=status)
    assert response.status_code == 303
    return int(urlparse(response.headers["location"]).path.split("/")[-1])


def create_template(client, name="Standard", amount="50.00"):
    from tests.helpers import in_admin_scope

    return in_admin_scope(
        client, lambda: client.app.state.fees.create_template(user=None, name=name, amount=amount)
    )


def add_student(
    client,
    class_id=1,
    first_name="Ada",
    last_name="Lovelace",
    enrolled_on="",
    fee_template_id="",
    custom_amount="50.00",
):
    """Add a student through the route. A custom monthly amount is the default
    billing source so most tests need no fee template setup."""
    return client.post(
        f"/classes/{class_id}/students",
        data={
            "first_name": first_name,
            "last_name": last_name,
            "enrolled_on": enrolled_on,
            "fee_template_id": fee_template_id,
            "custom_amount": custom_amount,
        },
        follow_redirects=False,
    )


def record_payment(client, student_id, amount, month="3", year="2026", paid_on="2026-03-10"):
    """Record a payment tagged to one month through the route."""
    response = client.post(
        "/payments/record",
        data={
            "student_id": str(student_id),
            "amount": amount,
            "method": "cash",
            "paid_on": paid_on,
            "month": month,
            "year": year,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def make_billed_student(client, name="Grade 1", first_name="Ada", last_name="Lovelace"):
    """A class with one student billed from March 2026 (back-dated enrollment)."""
    class_id = create_class_id(client, name=name)
    add_student(client, class_id, first_name=first_name, last_name=last_name, enrolled_on="2026-03-01")
    return class_id


def student_ids(client):
    from app.models import Student

    with client.app.state.db.session() as session:
        return {student.full_name: student.id for student in session.query(Student).all()}


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


def test_no_billed_months_hides_the_paid_ui(client):
    authenticated_admin(client)
    create_class(client)

    response = client.get("/students")

    assert response.status_code == 200
    assert "Paid" not in response.text
    assert "All statuses" not in response.text


def test_billed_months_show_the_month_and_status_filters(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")

    response = client.get("/students")

    assert response.status_code == 200
    assert "March 2026" in response.text  # month dropdown, from back-dated enrollment
    assert "Paid" in response.text  # paid column header
    assert "All statuses" in response.text  # status dropdown


def test_month_dropdown_defaults_to_the_most_recent_billed_month(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    today = date.today()
    current_period = f"{today.year:04d}-{today.month:02d}"

    response = client.get("/students")

    # An active student is owed through the current month, which is therefore
    # the most recent billed month and the dropdown default.
    assert response.status_code == 200
    assert f'value="{current_period}" selected' in response.text


def test_paid_column_shows_badges_and_remaining_amounts(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")
    record_payment(client, student_ids(client)["Ada Lovelace"], "50.00")

    response = client.get("/students?period=2026-03")

    assert response.status_code == 200
    assert "Paid" in response.text
    assert "Unpaid" in response.text
    assert "$50.00" in response.text  # Grace Hopper's remaining amount


def test_status_filter_excludes_never_billed_students(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    create_class_id(client, name="Grade 2")
    add_student(client, class_id=2, first_name="Grace", last_name="Hopper")

    response = client.get("/students?period=2026-03&status=unpaid")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text


def test_all_statuses_shows_everyone_including_never_billed(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    create_class_id(client, name="Grade 2")
    add_student(client, class_id=2, first_name="Grace", last_name="Hopper")

    response = client.get("/students?period=2026-03")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" in response.text


def test_paid_filter_combines_with_class_and_name(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Ada", last_name="Byron")

    response = client.get("/students?period=2026-03&status=unpaid&class_id=2&q=ada")

    assert response.status_code == 200
    assert "Ada Byron" in response.text
    assert "Ada Lovelace" not in response.text


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


def test_add_student_requires_a_billing_source(client):
    authenticated_admin(client)
    create_class(client)

    response = add_student(client, custom_amount="", fee_template_id="")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/1?err=")

    detail = client.get(response.headers["location"])
    assert "Choose a fee template or enter a monthly amount" in detail.text


def test_add_student_with_an_invalid_custom_amount_is_refused(client):
    authenticated_admin(client)
    create_class(client)

    response = add_student(client, custom_amount="0")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/classes/1?err=")

    detail = client.get(response.headers["location"])
    assert "Monthly amount must be greater than zero" in detail.text


def test_add_student_accepts_a_linked_template(client):
    authenticated_admin(client)
    create_class(client)
    template = create_template(client, name="Standard", amount="80.00")

    response = add_student(client, fee_template_id=str(template.id), custom_amount="")
    assert response.status_code == 303

    detail = client.get("/classes/1")
    assert "Ada Lovelace" in detail.text


def test_add_student_accepts_a_back_dated_enrolled_on(client):
    authenticated_admin(client)
    create_class(client)

    response = add_student(client, enrolled_on="2026-01-15")
    assert response.status_code == 303

    # The owed months run from the enrollment month, so January appears.
    search = client.get("/students")
    assert "January 2026" in search.text


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
        data={"enrolled_on": "", "fee_template_id": "", "custom_amount": "50.00"},
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
        data={"enrolled_on": "", "fee_template_id": "", "custom_amount": "50.00"},
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
        data={"enrolled_on": "", "fee_template_id": "", "custom_amount": "50.00"},
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


def test_edit_student_form_shows_the_current_amount(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    form = client.get("/students/1/edit")
    assert form.status_code == 200
    assert "Currently" in form.text
    assert "50.00" in form.text
    assert "Effective from" in form.text


def test_edit_student_changes_the_monthly_amount_from_an_effective_month(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client, enrolled_on="2026-03-01")

    response = client.post(
        "/students/1/edit",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "custom_amount": "75.00",
            "effective_month": "2026-06",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    account = client.get("/students/1/account")
    assert "June 2026" in account.text
    assert "75.00" in account.text
    assert "50.00" in account.text


def test_edit_student_links_a_template_from_an_effective_month(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client, enrolled_on="2026-03-01")
    template = create_template(client, name="Standard", amount="80.00")

    response = client.post(
        "/students/1/edit",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "fee_template_id": str(template.id),
            "effective_month": "2026-07",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    account = client.get("/students/1/account")
    assert "July 2026" in account.text
    assert "80.00" in account.text


def test_names_only_edit_leaves_the_amount_untouched(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    client.post(
        "/students/1/edit",
        data={"first_name": "Ada", "last_name": "King"},
        follow_redirects=False,
    )

    audit = client.get("/audit")
    assert "monthly amount" not in audit.text
    assert "Updated student Ada Lovelace to Ada King" in audit.text


def test_edit_student_amount_change_is_audited(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client, enrolled_on="2026-03-01")

    client.post(
        "/students/1/edit",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "custom_amount": "75.00",
            "effective_month": "2026-06",
        },
        follow_redirects=False,
    )

    response = client.get("/audit")
    assert "Changed Ada Lovelace" in response.text
    assert "$75.00" in response.text
    assert "effective June 2026" in response.text


def test_edit_student_rejects_an_invalid_effective_month(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.post(
        "/students/1/edit",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "custom_amount": "75.00",
            "effective_month": "2026-13",
        },
    )
    assert response.status_code == 400
    assert "Choose a valid effective month" in response.text


def test_edit_student_rejects_an_invalid_custom_amount(client):
    authenticated_admin(client)
    create_class(client)
    add_student(client)

    response = client.post(
        "/students/1/edit",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "custom_amount": "0",
            "effective_month": "2026-06",
        },
    )
    assert response.status_code == 400
    assert "Monthly amount must be greater than zero" in response.text


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


def test_account_page_renders_the_per_month_comparison_for_a_logged_in_user(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    sid = student_ids(client)["Ada Lovelace"]

    response = client.get(f"/students/{sid}/account")

    assert response.status_code == 200
    for header in ("Month", "Expected", "Waivers", "Paid", "Credit", "Remaining", "Status"):
        assert header in response.text
    assert "Total" in response.text
    assert "Student statement" in response.text
    assert "Print statement" in response.text


def test_account_page_404s_for_a_missing_student(client):
    authenticated_admin(client)
    create_class(client)

    assert client.get("/students/999/account").status_code == 404


# ---------------------------------------------------------------------------
# Two-campus scoping
# ---------------------------------------------------------------------------


def test_campus_scoping_isolates_classes_and_students(client):
    from app.auth.service import hash_password
    from app.models import Campus, Class, School, Student, User, UserRoles
    from tests.helpers import login

    authenticated_admin(client)
    with client.app.state.db.session() as session:
        school = session.query(School).first()
        campus_a = session.query(Campus).first()
        admin = session.query(User).filter_by(username="admin").one()
        admin.school_id = school.id
        admin.campus_id = campus_a.id
        campus_b = Campus(school_id=school.id, name="Campus B")
        session.add(campus_b)
        session.flush()
        class_a = Class(name="Grade A", campus_id=campus_a.id)
        class_b = Class(name="Grade B", campus_id=campus_b.id)
        session.add_all([class_a, class_b])
        session.flush()
        session.add_all(
            [
                Student(
                    class_id=class_a.id,
                    campus_id=campus_a.id,
                    first_name="Ada",
                    last_name="Lovelace",
                ),
                Student(
                    class_id=class_b.id,
                    campus_id=campus_b.id,
                    first_name="Grace",
                    last_name="Hopper",
                ),
            ]
        )
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
        class_a_id, class_b_id = class_a.id, class_b.id

    # The implicit admin sees only their own campus's class and student.
    detail = client.get(f"/classes/{class_a_id}")
    assert "Ada Lovelace" in detail.text
    assert "Grace Hopper" not in detail.text
    search = client.get("/students?q=hopper")
    assert "Grace Hopper" not in search.text
    assert "No students found" in search.text
    assert add_student(client, class_id=class_b_id).status_code == 404

    # The second-campus admin sees only theirs; the other campus is 404.
    client.post("/logout", follow_redirects=False)
    login(client, username="admin_b", password="password b")
    assert add_student(client, class_id=class_a_id).status_code == 404
    detail = client.get(f"/classes/{class_b_id}")
    assert "Grace Hopper" in detail.text
    assert "Ada Lovelace" not in detail.text
    search = client.get("/students?q=lovelace")
    assert "Ada Lovelace" not in search.text
    assert "No students found" in search.text

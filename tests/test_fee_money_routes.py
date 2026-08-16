"""Fee & money-flow route scoping (multi-school 04).

Role-authenticated route tests with two Campuses, following ticket 03's
pattern in ``test_students_routes.py``: the implicit Admin is bound to the
bootstrap Campus A, a second Admin is bound to Campus B, and each sees only its
own fee templates, closed months, expense categories, payments, and expenses.
Cross-campus ids are refused (404 or a redirected error), never data. The
service-level rules these routes wire to live in ``test_fee_money_scope.py``.
"""

from urllib.parse import parse_qs, urlparse

from app.auth.service import hash_password
from app.models import (
    Campus,
    Class,
    ClosedMonth,
    Expense,
    ExpenseCategory,
    FeeTemplate,
    Payment,
    School,
    Student,
    User,
    UserRoles,
)

from tests.helpers import PASSWORD, login


def create_template(client, name="Standard", amount="100.00"):
    return client.post(
        "/fees/templates",
        data={"name": name, "amount": amount},
        follow_redirects=False,
    )


def add_closed_month(client, month="7", year="2026"):
    return client.post(
        "/fees/closed-months",
        data={"month": month, "year": year},
        follow_redirects=False,
    )


def remove_closed_month(client, month="7", year="2026"):
    return client.post(
        "/fees/closed-months/remove",
        data={"month": month, "year": year},
        follow_redirects=False,
    )


def add_category(client, name):
    return client.post(
        "/expenses/categories",
        data={"name": name},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )


def record_expense(client, category_id, description="Chalk", amount="10.00"):
    return client.post(
        "/expenses",
        data={
            "category_id": str(category_id),
            "description": description,
            "amount": amount,
            "method": "cash",
            "occurred_on": "2026-08-06",
        },
        follow_redirects=False,
    )


def record_payment(client, student_id, amount="50.00"):
    return client.post(
        "/payments/record",
        data={
            "student_id": str(student_id),
            "amount": amount,
            "method": "cash",
            "paid_on": "2026-03-10",
            "month": "3",
            "year": "2026",
        },
        follow_redirects=False,
    )


def seed_two_campuses(client) -> dict[str, int]:
    """Bind the implicit Admin to Campus A and create Campus B + its Admin.

    Returns the ids a test needs: one class, one student, and one Campus-B-only
    fee template per setup.
    """
    from tests.helpers import authenticated_admin

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
        template_b = FeeTemplate(name="Standard B", amount_cents=10000, campus_id=campus_b.id)
        session.add_all([class_a, class_b, template_b])
        session.flush()
        student_a = Student(
            class_id=class_a.id,
            campus_id=campus_a.id,
            first_name="Ada",
            last_name="Lovelace",
        )
        student_b = Student(
            class_id=class_b.id,
            campus_id=campus_b.id,
            first_name="Grace",
            last_name="Hopper",
        )
        session.add_all([student_a, student_b])
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
        return {
            "campus_a_id": campus_a.id,
            "campus_b_id": campus_b.id,
            "class_a_id": class_a.id,
            "class_b_id": class_b.id,
            "student_a_id": student_a.id,
            "student_b_id": student_b.id,
            "template_b_id": template_b.id,
        }


def login_as_b(client) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, username="admin_b", password="password b")


def login_as_a(client) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, password=PASSWORD)


# ---------------------------------------------------------------------------
# Fee templates
# ---------------------------------------------------------------------------


def test_fee_templates_are_per_campus(client):
    ids = seed_two_campuses(client)

    response = create_template(client, name="Standard A", amount="100.00")
    assert response.status_code == 303

    page = client.get("/fees")
    assert "Standard A" in page.text
    assert "Standard B" not in page.text  # Campus B's seeded template stays hidden

    # Cross-campus ids are refused at the route, not just hidden.
    assert client.get(f"/fees/templates/{ids['template_b_id']}/edit-form").status_code == 404
    assert (
        client.post(
            f"/fees/templates/{ids['template_b_id']}/archive", follow_redirects=False
        ).status_code
        == 404
    )

    login_as_b(client)
    page = client.get("/fees")
    assert "Standard B" in page.text
    assert "Standard A" not in page.text

    with client.app.state.db.session() as session:
        assert {t.campus_id for t in session.query(FeeTemplate).all()} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }


# ---------------------------------------------------------------------------
# Closed months
# ---------------------------------------------------------------------------


def test_closed_months_are_per_campus(client):
    ids = seed_two_campuses(client)

    assert add_closed_month(client, month="7", year="2026").status_code == 303

    # The same month may be closed on Campus B without a duplicate error.
    login_as_b(client)
    assert add_closed_month(client, month="7", year="2026").status_code == 303
    assert add_closed_month(client, month="8", year="2026").status_code == 303

    with client.app.state.db.session() as session:
        rows = session.query(ClosedMonth).all()
        assert len(rows) == 3
        assert {row.campus_id for row in rows} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }

    # Each campus's page lists only its own closed months.
    page = client.get("/fees")
    assert "July 2026" in page.text
    assert "August 2026" in page.text

    login_as_a(client)
    page = client.get("/fees")
    assert "July 2026" in page.text
    assert "August 2026" not in page.text

    # Reopening a month closed on the other campus is refused.
    response = remove_closed_month(client, month="8", year="2026")
    assert response.status_code == 303
    err = parse_qs(urlparse(response.headers["location"]).query).get("err", [""])[0]
    assert "not on the closed list" in err


# ---------------------------------------------------------------------------
# Expense categories
# ---------------------------------------------------------------------------


def test_expense_categories_are_per_campus(client):
    ids = seed_two_campuses(client)

    assert add_category(client, "Salaries").status_code == 200
    login_as_b(client)
    # The same name is fine on Campus B (per-campus uniqueness, MD-3).
    assert add_category(client, "Salaries").status_code == 200

    with client.app.state.db.session() as session:
        rows = session.query(ExpenseCategory).all()
        assert len(rows) == 2
        assert {row.campus_id for row in rows} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }
        category_b_id = (
            session.query(ExpenseCategory)
            .filter(ExpenseCategory.campus_id == ids["campus_b_id"])
            .one()
            .id
        )

    # Renaming Campus B's category as Campus A's admin is refused.
    login_as_a(client)
    response = client.post(
        f"/expenses/categories/{category_b_id}/rename",
        data={"name": "Payroll"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "No expense category with id" in response.text


# ---------------------------------------------------------------------------
# Payments & credits
# ---------------------------------------------------------------------------


def test_payments_are_scoped_to_the_acting_campus(client):
    ids = seed_two_campuses(client)

    response = record_payment(client, ids["student_a_id"], amount="50.00")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/payments/")

    # A payment against the other campus's student is refused.
    assert record_payment(client, ids["student_b_id"], amount="50.00").status_code == 404

    # Each campus's payment picker lists only its own students.
    page = client.get("/payments?q=lovelace")
    assert "Ada Lovelace" in page.text
    page = client.get("/payments?q=hopper")
    assert "Grace Hopper" not in page.text

    login_as_b(client)
    response = record_payment(client, ids["student_b_id"], amount="25.00")
    assert response.status_code == 303
    payment_b_id = int(urlparse(response.headers["location"]).path.rstrip("/").split("/")[-2])
    page = client.get("/payments?q=hopper")
    assert "Grace Hopper" in page.text
    page = client.get("/payments?q=lovelace")
    assert "Ada Lovelace" not in page.text

    # Campus A's admin cannot open Campus B's receipt.
    login_as_a(client)
    assert client.get(f"/payments/{payment_b_id}/receipt").status_code == 404


def test_payment_rows_are_stamped_with_the_acting_campus(client):
    ids = seed_two_campuses(client)

    record_payment(client, ids["student_a_id"], amount="50.00")
    login_as_b(client)
    record_payment(client, ids["student_b_id"], amount="25.00")

    with client.app.state.db.session() as session:
        payments = session.query(Payment).all()
        assert len(payments) == 2
        assert {p.campus_id for p in payments} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


def test_expenses_record_only_under_own_campus_categories(client):
    ids = seed_two_campuses(client)

    add_category(client, "Supplies")
    with client.app.state.db.session() as session:
        category_a_id = (
            session.query(ExpenseCategory)
            .filter(ExpenseCategory.campus_id == ids["campus_a_id"])
            .one()
            .id
        )
    response = record_expense(client, category_a_id, description="Chalk")
    assert response.status_code == 303

    login_as_b(client)
    add_category(client, "Transport")
    with client.app.state.db.session() as session:
        category_b_id = (
            session.query(ExpenseCategory)
            .filter(ExpenseCategory.campus_id == ids["campus_b_id"])
            .one()
            .id
        )
    response = record_expense(client, category_b_id, description="Van fuel")
    assert response.status_code == 303

    # Campus A cannot record under Campus B's category.
    login_as_a(client)
    response = record_expense(client, category_b_id, description="Hijack")
    assert response.status_code == 303
    err = parse_qs(urlparse(response.headers["location"]).query).get("err", [""])[0]
    assert "No active expense category with id" in err

    # Each campus's expenses page shows only its own rows.
    page = client.get("/expenses")
    assert "Chalk" in page.text
    assert "Van fuel" not in page.text

    login_as_b(client)
    page = client.get("/expenses")
    assert "Van fuel" in page.text
    assert "Chalk" not in page.text

    with client.app.state.db.session() as session:
        expenses = session.query(Expense).all()
        assert len(expenses) == 2
        assert {e.campus_id for e in expenses} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }

"""Reports, dashboard, and arrears route scoping (multi-school 05).

Role-authenticated route tests with two Campuses, following ticket 04's pattern
in ``test_fee_money_routes.py``: the implicit Admin is bound to Campus A, a
second Admin to Campus B. Each admin records money against their own campus and
every report page, CSV export, the dashboard KPIs/charts, the class filter
dropdown, and the arrears page reflect only the acting Campus — the other
Campus's students, categories, and amounts never leak. Cross-campus class ids
are refused (404), never data. The service-level rules live in
``test_reports_scope.py``.
"""

from datetime import date

from app.models import ExpenseCategory, Student, StudentAmountChange

from tests.test_fee_money_routes import (
    add_category,
    login_as_a,
    login_as_b,
    seed_two_campuses,
)


def record_payment(client, student_id, amount, today):
    return client.post(
        "/payments/record",
        data={
            "student_id": str(student_id),
            "amount": amount,
            "method": "cash",
            "paid_on": today.isoformat(),
            "month": str(today.month),
            "year": str(today.year),
        },
        follow_redirects=False,
    )


def record_expense(client, category_id, description, today, amount="20.00"):
    return client.post(
        "/expenses",
        data={
            "category_id": str(category_id),
            "description": description,
            "amount": amount,
            "method": "cash",
            "occurred_on": today.isoformat(),
        },
        follow_redirects=False,
    )


def enroll_and_charge(client, ids, today, amount_cents=10000):
    """Both seeded students owe the current month's fee."""
    with client.app.state.db.session() as session:
        for sid in (ids["student_a_id"], ids["student_b_id"]):
            student = session.get(Student, sid)
            student.enrolled_on = date(today.year, today.month, 1)
            session.add(
                StudentAmountChange(
                    student_id=sid,
                    campus_id=student.campus_id,
                    amount_cents=amount_cents,
                    month=today.month,
                    year=today.year,
                )
            )
        session.commit()


def seed_current_month_money(client):
    """Campus A: Ada pays half and spends on Supplies.
    Campus B: Grace pays nothing and spends on Transport.
    """
    ids = seed_two_campuses(client)
    today = date.today()
    enroll_and_charge(client, ids, today)

    assert record_payment(client, ids["student_a_id"], "50.00", today).status_code == 303
    add_category(client, "Supplies")
    with client.app.state.db.session() as session:
        category_a_id = (
            session.query(ExpenseCategory)
            .filter(ExpenseCategory.campus_id == ids["campus_a_id"])
            .one()
            .id
        )
    assert record_expense(client, category_a_id, "Chalk", today).status_code == 303

    login_as_b(client)
    add_category(client, "Transport")
    with client.app.state.db.session() as session:
        category_b_id = (
            session.query(ExpenseCategory)
            .filter(ExpenseCategory.campus_id == ids["campus_b_id"])
            .one()
            .id
        )
    assert record_expense(client, category_b_id, "Van fuel", today, amount="10.00").status_code == 303
    login_as_a(client)

    ids["category_a_id"] = category_a_id
    ids["category_b_id"] = category_b_id
    return ids


def current_period():
    today = date.today()
    return f"month={today.month}&year={today.year}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_kpis_and_activity_are_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get("/")
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text  # Campus A's recent payment
    assert "$50.00" in page.text  # collected this month
    assert "Supplies" in page.text  # Campus A's recent expense
    assert "Grace Hopper" not in page.text
    assert "Transport" not in page.text
    assert "$10.00" not in page.text

    login_as_b(client)
    page = client.get("/")
    assert page.status_code == 200
    assert "$100.00" in page.text  # Grace's outstanding arrears
    assert "$10.00" in page.text  # Campus B's expenses
    assert "Transport" in page.text
    assert "Ada Lovelace" not in page.text
    assert "Supplies" not in page.text
    assert "$50.00" not in page.text


def test_dashboard_records_are_stamped_per_campus(client):
    ids = seed_current_month_money(client)

    from app.models import Expense, Payment

    with client.app.state.db.session() as session:
        payments = session.query(Payment).all()
        assert {p.campus_id for p in payments} == {ids["campus_a_id"]}
        expenses = session.query(Expense).all()
        assert {e.campus_id for e in expenses} == {
            ids["campus_a_id"],
            ids["campus_b_id"],
        }


# ---------------------------------------------------------------------------
# Arrears
# ---------------------------------------------------------------------------


def test_arrears_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get("/arrears")
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text
    assert "$50.00" in page.text  # 100.00 fee minus 50.00 paid
    assert "Grace Hopper" not in page.text

    login_as_b(client)
    page = client.get("/arrears")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "$100.00" in page.text  # unpaid in full
    assert "Ada Lovelace" not in page.text


# ---------------------------------------------------------------------------
# Income vs Expense
# ---------------------------------------------------------------------------


def test_income_vs_expense_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get(f"/reports/income-expense?{current_period()}")
    assert page.status_code == 200
    assert "$50.00" in page.text  # income
    assert "$20.00" in page.text  # expenses
    assert "$10.00" not in page.text

    login_as_b(client)
    page = client.get(f"/reports/income-expense?{current_period()}")
    assert page.status_code == 200
    assert "$10.00" in page.text  # expenses
    assert "$50.00" not in page.text
    assert "$20.00" not in page.text


def test_income_vs_expense_csv_is_per_campus(client):
    ids = seed_current_month_money(client)

    response = client.get(f"/reports/income-expense.csv?{current_period()}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "50.00" in response.text
    assert "10.00" not in response.text

    login_as_b(client)
    response = client.get(f"/reports/income-expense.csv?{current_period()}")
    assert "10.00" in response.text
    assert "50.00" not in response.text


# ---------------------------------------------------------------------------
# Expense by category
# ---------------------------------------------------------------------------


def test_expense_by_category_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get(f"/reports/expense-category?{current_period()}")
    assert page.status_code == 200
    assert "Supplies" in page.text
    assert "$20.00" in page.text
    assert "Transport" not in page.text

    login_as_b(client)
    page = client.get(f"/reports/expense-category?{current_period()}")
    assert page.status_code == 200
    assert "Transport" in page.text
    assert "$10.00" in page.text
    assert "Supplies" not in page.text


def test_expense_by_category_csv_is_per_campus(client):
    ids = seed_current_month_money(client)

    response = client.get(f"/reports/expense-category.csv?{current_period()}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Supplies" in response.text
    assert "Transport" not in response.text

    login_as_b(client)
    response = client.get(f"/reports/expense-category.csv?{current_period()}")
    assert "Transport" in response.text
    assert "Supplies" not in response.text


# ---------------------------------------------------------------------------
# Paid students
# ---------------------------------------------------------------------------


def test_paid_students_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get(f"/reports/paid-students?{current_period()}")
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text
    assert "Partial" in page.text
    assert "Grace Hopper" not in page.text

    login_as_b(client)
    page = client.get(f"/reports/paid-students?{current_period()}")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "Unpaid" in page.text
    assert "Ada Lovelace" not in page.text


def test_paid_students_csv_is_per_campus(client):
    ids = seed_current_month_money(client)

    response = client.get(f"/reports/paid-students.csv?{current_period()}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text

    login_as_b(client)
    response = client.get(f"/reports/paid-students.csv?{current_period()}")
    assert "Grace Hopper" in response.text
    assert "Ada Lovelace" not in response.text


def test_paid_students_refuses_a_foreign_class(client):
    ids = seed_current_month_money(client)

    response = client.get(
        f"/reports/paid-students?{current_period()}&class_id={ids['class_b_id']}"
    )
    assert response.status_code == 404

    login_as_b(client)
    response = client.get(
        f"/reports/paid-students?{current_period()}&class_id={ids['class_a_id']}"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Summarized finance
# ---------------------------------------------------------------------------


def test_summary_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get(f"/reports/summary?{current_period()}")
    assert page.status_code == 200
    assert "$50.00" in page.text  # income
    assert "$20.00" in page.text  # expenses
    assert "Outstanding unpaid fees" in page.text
    assert "$10.00" not in page.text

    login_as_b(client)
    page = client.get(f"/reports/summary?{current_period()}")
    assert page.status_code == 200
    assert "$10.00" in page.text  # expenses
    assert "$50.00" not in page.text
    assert "$20.00" not in page.text


def test_summary_csv_is_per_campus(client):
    ids = seed_current_month_money(client)

    response = client.get(f"/reports/summary.csv?{current_period()}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "50.00" in response.text
    assert "10.00" not in response.text

    login_as_b(client)
    response = client.get(f"/reports/summary.csv?{current_period()}")
    assert "10.00" in response.text
    assert "50.00" not in response.text


# ---------------------------------------------------------------------------
# Student list
# ---------------------------------------------------------------------------


def test_student_list_page_is_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get("/reports/students")
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text
    assert "Grade A" in page.text
    assert "Grace Hopper" not in page.text
    assert "Grade B" not in page.text

    login_as_b(client)
    page = client.get("/reports/students")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "Grade B" in page.text
    assert "Ada Lovelace" not in page.text
    assert "Grade A" not in page.text


def test_student_list_csv_is_per_campus(client):
    ids = seed_current_month_money(client)

    response = client.get("/reports/students.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text

    login_as_b(client)
    response = client.get("/reports/students.csv")
    assert "Grace Hopper" in response.text
    assert "Ada Lovelace" not in response.text


def test_student_list_refuses_a_foreign_class(client):
    ids = seed_current_month_money(client)

    assert client.get(f"/reports/students?class_id={ids['class_b_id']}").status_code == 404
    login_as_b(client)
    assert client.get(f"/reports/students?class_id={ids['class_a_id']}").status_code == 404


# ---------------------------------------------------------------------------
# Class filter dropdowns draw only from the acting Campus
# ---------------------------------------------------------------------------


def test_class_filter_dropdowns_are_per_campus(client):
    ids = seed_current_month_money(client)

    page = client.get(f"/reports/paid-students?{current_period()}")
    assert "Grade A" in page.text
    assert "Grade B" not in page.text

    login_as_b(client)
    page = client.get(f"/reports/paid-students?{current_period()}")
    assert "Grade B" in page.text
    assert "Grade A" not in page.text

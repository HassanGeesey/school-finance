"""Reports & dashboard routes end-to-end: pages and CSV exports.

Route-level smoke tests of the thin adapters + templates. Business rules (what
counts as income/expense/arrears, grouping, statuses, who is included) live in
``test_reports_service.py``. Every report renders a page and a CSV export; any
logged-in user — including a Finance officer — may view them; role gating is
asserted here.
"""

from urllib.parse import urlparse

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


def generate_fees(client, class_id, month="3", year="2026"):
    response = client.post(
        "/fees/generate",
        data={"class_id": str(class_id), "month": month, "year": year},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200


def record_payment(client, student_id, amount, paid_on="2026-03-10"):
    response = client.post(
        "/payments/record",
        data={"student_id": str(student_id), "amount": amount, "method": "cash", "paid_on": paid_on},
        follow_redirects=False,
    )
    assert response.status_code == 303


def add_category(client, name="Utilities"):
    response = client.post(
        "/expenses/categories",
        data={"name": name},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200


def record_expense(client, category_id, amount="20.00", occurred_on="2026-03-15"):
    response = client.post(
        "/expenses",
        data={
            "category_id": str(category_id),
            "description": "Bus fuel",
            "amount": amount,
            "method": "cash",
            "occurred_on": occurred_on,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200


def category_ids(client):
    from app.models import ExpenseCategory

    with client.app.state.db.session() as session:
        return {category.name: category.id for category in session.query(ExpenseCategory).all()}


def student_ids(client):
    from app.models import Student

    with client.app.state.db.session() as session:
        return {student.full_name: student.id for student in session.query(Student).all()}


def make_billed_student(client, name="Grade 1", first_name="Ada", last_name="Lovelace"):
    class_id = create_class(client, name=name)
    add_fee_item(client, class_id)
    add_student(client, class_id, first_name=first_name, last_name=last_name)
    generate_fees(client, class_id)
    return class_id


def assert_csv(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


# ---------------------------------------------------------------------------
# Login / role gating
# ---------------------------------------------------------------------------


def test_reports_page_requires_login(client):
    setup_admin(client)

    response = client.get("/reports", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_a_finance_officer_can_view_the_reports_hub(client):
    authenticated_admin(client)
    add_finance_user(client)
    login_finance(client)

    response = client.get("/reports")

    assert response.status_code == 200
    assert "Income vs Expense" in response.text
    assert "Expense by category" in response.text
    assert "Paid students" in response.text
    assert "Summarized finance" in response.text
    assert "Student list" in response.text


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_shows_kpis_charts_and_recent_activity(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "30.00", paid_on="2026-08-06")
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"], amount="20.00", occurred_on="2026-08-06")

    response = client.get("/")

    assert response.status_code == 200
    assert "$30.00" in response.text  # collected this month
    assert "$20.00" in response.text  # outstanding arrears (50 - 30) and expenses
    assert "Ada Lovelace" in response.text  # recent payment
    assert "canvas" in response.text  # Chart.js charts render
    assert "/reports" in response.text  # quick action links to reports


# ---------------------------------------------------------------------------
# Income vs Expense
# ---------------------------------------------------------------------------


def test_income_vs_expense_page_renders_month_totals(client):
    authenticated_admin(client)
    make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "40.00")
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"])

    response = client.get("/reports/income-expense?month=3&year=2026")

    assert response.status_code == 200
    assert "March 2026" in response.text
    assert "$40.00" in response.text  # income
    assert "$20.00" in response.text  # expenses
    assert "$20.00" in response.text  # net
    assert "Cash" in response.text  # method breakdown


def test_income_vs_expense_csv_export(client):
    authenticated_admin(client)
    make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "40.00")

    response = client.get("/reports/income-expense.csv?month=3&year=2026")

    assert_csv(response)
    assert "March 2026" in response.text
    assert "40.00" in response.text
    assert "20.00" not in response.text


# ---------------------------------------------------------------------------
# Expense by category
# ---------------------------------------------------------------------------


def test_expense_by_category_page_groups_and_orders(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    add_category(client, "Transport")
    utilities = category_ids(client)["Utilities"]
    transport = category_ids(client)["Transport"]
    record_expense(client, utilities, amount="30.00")
    record_expense(client, transport, amount="20.00")
    record_expense(client, utilities, amount="10.00", occurred_on="2026-02-05")

    response = client.get("/reports/expense-category")

    assert response.status_code == 200
    assert "Utilities" in response.text
    assert "Transport" in response.text
    assert "$60.00" in response.text  # all-time total


def test_expense_by_category_page_filters_to_one_month(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"], amount="30.00")
    record_expense(client, category_ids(client)["Utilities"], amount="10.00", occurred_on="2026-02-05")

    response = client.get("/reports/expense-category?month=3&year=2026")

    assert response.status_code == 200
    assert "$30.00" in response.text  # March only
    assert "$10.00" not in response.text


def test_expense_by_category_csv_export(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"])

    response = client.get("/reports/expense-category.csv?month=3&year=2026")

    assert_csv(response)
    assert "Utilities" in response.text
    assert "20.00" in response.text


# ---------------------------------------------------------------------------
# Paid students
# ---------------------------------------------------------------------------


def test_paid_students_page_lists_statuses(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")
    record_payment(client, student_ids(client)["Ada Lovelace"], "30.00")

    response = client.get("/reports/paid-students?month=3&year=2026")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" in response.text
    assert "Partial" in response.text
    assert "Unpaid" in response.text


def test_paid_students_page_filters_by_class(client):
    authenticated_admin(client)
    grade_1 = make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")

    response = client.get(f"/reports/paid-students?month=3&year=2026&class_id={grade_1}")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text


def test_paid_students_csv_export(client):
    authenticated_admin(client)
    make_billed_student(client)
    record_payment(client, student_ids(client)["Ada Lovelace"], "50.00")

    response = client.get("/reports/paid-students.csv?month=3&year=2026")

    assert_csv(response)
    assert "Ada Lovelace" in response.text
    assert "paid" in response.text


# ---------------------------------------------------------------------------
# Summarized finance
# ---------------------------------------------------------------------------


def test_summary_page_rolls_up_totals(client):
    authenticated_admin(client)
    make_billed_student(client)
    record_payment(client, student_ids(client)["Ada Lovelace"], "40.00")
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"])

    response = client.get("/reports/summary?month=3&year=2026")

    assert response.status_code == 200
    assert "$40.00" in response.text  # income
    assert "$20.00" in response.text  # expenses
    assert "$20.00" in response.text  # net
    assert "Outstanding arrears" in response.text
    assert "Credit balances" in response.text


def test_summary_csv_export(client):
    authenticated_admin(client)
    make_billed_student(client)
    record_payment(client, student_ids(client)["Ada Lovelace"], "40.00")

    response = client.get("/reports/summary.csv?month=3&year=2026")

    assert_csv(response)
    assert "40.00" in response.text
    assert "Outstanding arrears" in response.text


# ---------------------------------------------------------------------------
# Student list
# ---------------------------------------------------------------------------


def test_student_list_page_lists_all_students(client):
    authenticated_admin(client)
    make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")

    response = client.get("/reports/students")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" in response.text
    assert "$50.00" in response.text  # monthly fee


def test_student_list_page_filters_by_class(client):
    authenticated_admin(client)
    grade_1 = make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")

    response = client.get(f"/reports/students?class_id={grade_1}")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text


def test_student_list_csv_export(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/reports/students.csv")

    assert_csv(response)
    assert "Ada Lovelace" in response.text
    assert "50.00" in response.text


def test_report_sidebar_nav_highlights_reports(client):
    authenticated_admin(client)

    response = client.get("/reports")

    assert response.status_code == 200
    assert "/reports" in response.text
    assert "Reports" in response.text


# ---------------------------------------------------------------------------
# Filter form submission (period=YYYY-MM) — the path the UI forms use
# ---------------------------------------------------------------------------


def test_income_vs_expense_filters_by_period_param(client):
    authenticated_admin(client)
    make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "40.00")

    response = client.get("/reports/income-expense?period=2026-03")

    assert response.status_code == 200
    assert "$40.00" in response.text


def test_income_vs_expense_csv_filters_by_period_param(client):
    authenticated_admin(client)
    make_billed_student(client)
    student_id = student_ids(client)["Ada Lovelace"]
    record_payment(client, student_id, "40.00")

    response = client.get("/reports/income-expense.csv?period=2026-03")

    assert_csv(response)
    assert "40.00" in response.text


def test_expense_by_category_filters_by_period_param(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"], amount="30.00")
    record_expense(client, category_ids(client)["Utilities"], amount="10.00", occurred_on="2026-02-05")

    response = client.get("/reports/expense-category?period=2026-03")

    assert response.status_code == 200
    assert "$30.00" in response.text
    assert "$10.00" not in response.text


def test_paid_students_filters_by_period_and_class_params(client):
    authenticated_admin(client)
    grade_1 = make_billed_student(client, name="Grade 1")
    make_billed_student(client, name="Grade 2", first_name="Grace", last_name="Hopper")

    response = client.get(f"/reports/paid-students?period=2026-03&class_id={grade_1}")

    assert response.status_code == 200
    assert "Ada Lovelace" in response.text
    assert "Grace Hopper" not in response.text


# ---------------------------------------------------------------------------
# Robustness: bad input and CSV hygiene
# ---------------------------------------------------------------------------


def test_income_vs_expense_offers_billed_but_unpaid_months(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/reports/income-expense")

    assert response.status_code == 200
    assert "2026-03" in response.text  # billed month is selectable
    assert "March 2026" in response.text


def test_expense_by_category_month_title_shows_period_label(client):
    authenticated_admin(client)
    add_category(client, "Utilities")
    record_expense(client, category_ids(client)["Utilities"], amount="30.00")

    response = client.get("/reports/expense-category?period=2026-03")

    assert response.status_code == 200
    assert "Expenses by category, March 2026" in response.text


def test_reports_reject_an_invalid_month(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/reports/income-expense?period=2026-13")

    assert response.status_code == 400


def test_expense_by_category_rejects_an_invalid_month(client):
    authenticated_admin(client)

    response = client.get("/reports/expense-category?period=2026-00")

    assert response.status_code == 400


def test_paid_students_unknown_class_is_a_404(client):
    authenticated_admin(client)

    response = client.get("/reports/paid-students?month=3&year=2026&class_id=999")

    assert response.status_code == 404


def test_student_list_unknown_class_is_a_404(client):
    authenticated_admin(client)

    response = client.get("/reports/students?class_id=999")

    assert response.status_code == 404


def test_csv_export_has_bom_and_a_meaningful_filename(client):
    authenticated_admin(client)
    make_billed_student(client)

    response = client.get("/reports/paid-students.csv?month=3&year=2026")

    assert_csv(response)
    assert response.text.startswith("\ufeff")
    assert 'filename="paid-students.csv"' in response.headers["content-disposition"]

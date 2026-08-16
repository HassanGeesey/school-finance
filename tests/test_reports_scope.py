"""Reports & arrears scoping (multi-school 05).

Service-level tests with a seeded scope, following tickets 03-04's pattern: the
request scope resolves from the acting user and filters every report read.
Two Campuses of one School each hold their own payments, expenses, credits, and
students, so income-vs-expense, expense-by-category, paid-students, summarized
finance, the student register, the period dropdowns, the dashboard KPIs/charts,
and the arrears report all reflect only the acting Campus. A School-bound
Superadmin sees both Campuses. Route concerns live in ``test_reports_routes.py``.
"""

from datetime import date

import pytest

from app.arrears.service import ArrearsService
from app.charge_status import ChargeStatus
from app.classes.service import ClassNotFound
from app.models import (
    Class,
    Expense,
    ExpenseCategory,
    Payment,
    Student,
    StudentAmountChange,
)
from app.reports.service import ReportService
from app.tenants.scope import RequestScope, scope_context
from tests.test_tenant_scope import seed_tenant_world


@pytest.fixture()
def reports(db) -> ReportService:
    return ReportService(db, arrears=ArrearsService(db))


def billed_student(
    session,
    class_,
    campus_id,
    first,
    last,
    today,
    *,
    amount_cents=10000,
):
    """A student who owes the current month: enrolled the 1st, amount seeded."""
    student = Student(
        class_id=class_.id,
        campus_id=campus_id,
        first_name=first,
        last_name=last,
        enrolled_on=date(today.year, today.month, 1),
    )
    session.add(student)
    session.flush()
    session.add(
        StudentAmountChange(
            student_id=student.id,
            campus_id=campus_id,
            amount_cents=amount_cents,
            month=today.month,
            year=today.year,
        )
    )
    session.flush()
    return student


def payment(session, student, month, year, amount_cents, paid_on=None):
    payment = Payment(
        student_id=student.id,
        campus_id=student.campus_id,
        amount_cents=amount_cents,
        method="cash",
        paid_on=paid_on or date(year, month, 1),
        month=month,
        year=year,
    )
    session.add(payment)
    session.flush()
    return payment


def expense(session, campus_id, category_name, amount_cents, occurred_on):
    category = ExpenseCategory(name=category_name, campus_id=campus_id)
    session.add(category)
    session.flush()
    expense = Expense(
        category_id=category.id,
        campus_id=campus_id,
        description=f"{category_name} spend",
        amount_cents=amount_cents,
        method="cash",
        occurred_on=occurred_on,
    )
    session.add(expense)
    session.flush()
    return expense


def seed_current_month_money(session, campus_a, campus_b):
    """Current-month money per Campus: Ada (A) pays in full, Grace (B) does not."""
    today = date.today()
    class_a = Class(name="Grade A", campus_id=campus_a.id)
    class_b = Class(name="Grade B", campus_id=campus_b.id)
    session.add_all([class_a, class_b])
    session.flush()
    ada = billed_student(session, class_a, campus_a.id, "Ada", "Lovelace", today)
    grace = billed_student(session, class_b, campus_b.id, "Grace", "Hopper", today)
    payment(session, ada, today.month, today.year, 10000, paid_on=today)
    expense(session, campus_a.id, "Supplies", 2000, today)
    expense(session, campus_b.id, "Transport", 5000, today)
    session.commit()
    return class_a, class_b, ada, grace


# ---------------------------------------------------------------------------
# Income vs Expense
# ---------------------------------------------------------------------------


def test_income_vs_expense_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        report_a = reports.income_vs_expense(today.month, today.year)
    with scope_context(RequestScope.for_user(admin_b)):
        report_b = reports.income_vs_expense(today.month, today.year)
    with scope_context(RequestScope.for_user(superadmin)):
        report_sa = reports.income_vs_expense(today.month, today.year)

    assert (report_a.income_cents, report_a.expenses_cents, report_a.net_cents) == (
        10000,
        2000,
        8000,
    )
    assert (report_b.income_cents, report_b.expenses_cents, report_b.net_cents) == (
        0,
        5000,
        -5000,
    )
    assert (report_sa.income_cents, report_sa.expenses_cents, report_sa.net_cents) == (
        10000,
        7000,
        3000,
    )


# ---------------------------------------------------------------------------
# Expense by category
# ---------------------------------------------------------------------------


def test_expense_by_category_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        report_a = reports.expense_by_category()
    with scope_context(RequestScope.for_user(admin_b)):
        report_b = reports.expense_by_category()
    with scope_context(RequestScope.for_user(superadmin)):
        report_sa = reports.expense_by_category()

    assert report_a.total_cents == 2000
    assert [line.category_name for line in report_a.lines] == ["Supplies"]
    assert report_b.total_cents == 5000
    assert [line.category_name for line in report_b.lines] == ["Transport"]
    assert report_sa.total_cents == 7000
    assert [line.category_name for line in report_sa.lines] == ["Transport", "Supplies"]


# ---------------------------------------------------------------------------
# Paid students
# ---------------------------------------------------------------------------


def test_paid_students_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        report_a = reports.paid_students(today.month, today.year)
    with scope_context(RequestScope.for_user(admin_b)):
        report_b = reports.paid_students(today.month, today.year)
    with scope_context(RequestScope.for_user(superadmin)):
        report_sa = reports.paid_students(today.month, today.year)

    assert report_a.billed_count == 1
    assert report_a.lines[0].student.last_name == "Lovelace"
    assert report_a.lines[0].status == ChargeStatus.PAID
    assert report_b.billed_count == 1
    assert report_b.lines[0].student.last_name == "Hopper"
    assert report_b.lines[0].status == ChargeStatus.UNPAID
    assert report_sa.billed_count == 2


def test_paid_students_refuses_a_foreign_campus_class(reports, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _superadmin = seed_tenant_world(session)
    class_a, class_b, _ada, _grace = seed_current_month_money(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClassNotFound):
            reports.paid_students(today.month, today.year, class_id=class_b.id)
        # The acting Campus's own class still works.
        report = reports.paid_students(today.month, today.year, class_id=class_a.id)
    assert report.billed_count == 1


# ---------------------------------------------------------------------------
# Summarized finance
# ---------------------------------------------------------------------------


def test_finance_summary_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, _superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        summary_a = reports.finance_summary(today.month, today.year)
    with scope_context(RequestScope.for_user(admin_b)):
        summary_b = reports.finance_summary(today.month, today.year)

    assert (summary_a.income_cents, summary_a.expenses_cents) == (10000, 2000)
    assert summary_a.arrears_cents == 0
    assert (summary_b.income_cents, summary_b.expenses_cents) == (0, 5000)
    assert summary_b.arrears_cents == 10000  # Grace's unpaid month, not Ada's


# ---------------------------------------------------------------------------
# Student register
# ---------------------------------------------------------------------------


def test_student_list_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        report_a = reports.student_list()
    with scope_context(RequestScope.for_user(admin_b)):
        report_b = reports.student_list()
    with scope_context(RequestScope.for_user(superadmin)):
        report_sa = reports.student_list()

    assert [line.student.last_name for line in report_a.lines] == ["Lovelace"]
    assert [line.student.last_name for line in report_b.lines] == ["Hopper"]
    assert {line.student.last_name for line in report_sa.lines} == {
        "Lovelace",
        "Hopper",
    }


# ---------------------------------------------------------------------------
# Period dropdowns
# ---------------------------------------------------------------------------


def test_period_dropdowns_are_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    today = date.today()
    class_a = Class(name="Grade A", campus_id=campus_a.id)
    class_b = Class(name="Grade B", campus_id=campus_b.id)
    session.add_all([class_a, class_b])
    session.flush()
    ada = billed_student(session, class_a, campus_a.id, "Ada", "Lovelace", today)
    grace = billed_student(session, class_b, campus_b.id, "Grace", "Hopper", today)
    # Campus A's money lives in March 2026; Campus B's in April 2026.
    payment(session, ada, 3, 2026, 10000, paid_on=date(2026, 3, 10))
    expense(session, campus_a.id, "Supplies", 2000, date(2026, 3, 15))
    payment(session, grace, 4, 2026, 5000, paid_on=date(2026, 4, 10))
    expense(session, campus_b.id, "Transport", 1000, date(2026, 4, 15))
    session.commit()
    current = (today.month, today.year)

    with scope_context(RequestScope.for_user(admin_a)):
        periods_a = set(reports.list_periods())
        billed_a = set(reports.billed_periods())
    with scope_context(RequestScope.for_user(admin_b)):
        periods_b = set(reports.list_periods())
        billed_b = set(reports.billed_periods())
    with scope_context(RequestScope.for_user(superadmin)):
        periods_sa = set(reports.list_periods())

    assert periods_a == {(3, 2026), current}
    assert periods_b == {(4, 2026), current}
    assert periods_sa == {(3, 2026), (4, 2026), current}
    assert billed_a == {(3, 2026), current}
    assert billed_b == {(4, 2026), current}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_is_per_campus(reports, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        dash_a = reports.dashboard(today=today)
    with scope_context(RequestScope.for_user(admin_b)):
        dash_b = reports.dashboard(today=today)
    with scope_context(RequestScope.for_user(superadmin)):
        dash_sa = reports.dashboard(today=today)

    # KPIs.
    assert dash_a.collected_cents == 10000
    assert dash_a.expenses_cents == 2000
    assert dash_a.active_student_count == 1
    assert dash_a.arrears_cents == 0
    assert dash_b.collected_cents == 0
    assert dash_b.expenses_cents == 5000
    assert dash_b.active_student_count == 1
    assert dash_b.arrears_cents == 10000
    assert dash_sa.active_student_count == 2
    assert dash_sa.collected_cents == 10000

    # Recent activity.
    assert [p.student.last_name for p in dash_a.recent_payments] == ["Lovelace"]
    assert [p.student.last_name for p in dash_b.recent_payments] == []
    assert [e.category.name for e in dash_a.recent_expenses] == ["Supplies"]
    assert [e.category.name for e in dash_b.recent_expenses] == ["Transport"]

    # Charts: the six-month series and expense-by-category pie.
    current_month = (today.year, today.month)
    current_line = next(
        line
        for line in dash_a.monthly
        if (line.year, line.month) == current_month
    )
    assert (current_line.income_cents, current_line.expenses_cents) == (10000, 2000)
    assert dash_b.monthly[-1].income_cents == 0
    assert dash_b.monthly[-1].expenses_cents == 5000
    assert dash_a.arrears_band_counts == {}
    assert dash_b.arrears_band_counts != {}
    assert [line.category_name for line in dash_a.category_lines] == ["Supplies"]
    assert [line.category_name for line in dash_b.category_lines] == ["Transport"]


# ---------------------------------------------------------------------------
# Arrears report
# ---------------------------------------------------------------------------


def test_arrears_report_is_per_campus(db, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    seed_current_month_money(session, campus_a, campus_b)
    today = date.today()
    service = ArrearsService(db)

    with scope_context(RequestScope.for_user(admin_a)):
        lines_a = service.arrears_report(today=today)
    with scope_context(RequestScope.for_user(admin_b)):
        lines_b = service.arrears_report(today=today)
    with scope_context(RequestScope.for_user(superadmin)):
        lines_sa = service.arrears_report(today=today)

    assert lines_a == []  # Ada paid in full
    assert [line.student.last_name for line in lines_b] == ["Hopper"]
    assert lines_b[0].owed_cents == 10000
    assert [line.student.last_name for line in lines_sa] == ["Hopper"]

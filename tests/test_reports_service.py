"""Reports service: report aggregations and the dashboard.

Business rules only — the single testing seam. The reports feature is
read-only: it aggregates payments, expenses, charges, and arrears into the
report surfaces (income vs expense, expense by category, paid/unpaid students,
summarized finance, student lists) and the dashboard. Route concerns live in
``test_reports_routes.py``.
"""

from datetime import date

import pytest

from app.arrears.service import ArrearsService
from app.audit.service import AuditService
from app.classes.service import ClassService
from app.expenses.service import ExpenseService
from app.fees.service import AdjustmentsService, FeeService
from app.models import (
    Charge,
    ClassStatus,
    PaymentMethods,
    StudentStatus,
    User,
    UserRoles,
)
from app.payments.service import PaymentService
from app.reports.service import (
    PaidStatus,
    ReportService,
)
from app.students.service import StudentService

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


@pytest.fixture()
def fees(db, audit) -> FeeService:
    return FeeService(db, audit=audit)


@pytest.fixture()
def adjustments(db, audit) -> AdjustmentsService:
    return AdjustmentsService(db, audit=audit)


@pytest.fixture()
def payments(db, audit) -> PaymentService:
    return PaymentService(db, audit=audit)


@pytest.fixture()
def expenses(db, audit) -> ExpenseService:
    return ExpenseService(db, audit=audit)


@pytest.fixture()
def arrears(db) -> ArrearsService:
    return ArrearsService(db)


@pytest.fixture()
def reports(db, arrears) -> ReportService:
    return ReportService(db, arrears=arrears)


@pytest.fixture()
def admin(db, session) -> User:
    user = User(
        username="admin",
        name="Head Teacher",
        password_hash=PASSWORD,
        role=UserRoles.ADMIN,
    )
    session.add(user)
    session.commit()
    return user


def make_class(
    classes: ClassService, students: StudentService, fees: FeeService, admin: User, *, name="Grade 1",
    items: tuple[tuple[str, str], ...] = (("Tuition", "50.00"),),
    first_name: str = "Ada",
    last_name: str = "Lovelace",
) -> tuple[int, int]:
    cls = classes.create_class(user=admin, name=name)
    for item_name, amount in items:
        classes.add_fee_item(user=admin, class_id=cls.id, name=item_name, amount=amount)
    student = students.add_student(
        user=admin, class_id=cls.id, first_name=first_name, last_name=last_name
    )
    return student.id, cls.id


def bill(fees: FeeService, class_id: int, *, month: int, year: int = 2026, admin: User) -> None:
    fees.generate(user=admin, class_id=class_id, month=month, year=year)


def pay(payments: PaymentService, student_id: int, amount: str, admin: User, paid_on=date(2026, 8, 6)) -> None:
    payments.record_payment(
        user=admin, student_id=student_id, amount=amount, method="cash", paid_on=paid_on
    )


def spend(expenses: ExpenseService, category_name: str, amount: str, admin: User, occurred_on=date(2026, 8, 6)) -> int:
    existing = {category.name: category for category in expenses.list_categories(include_archived=True)}
    category = existing.get(category_name)
    if category is None:
        category = expenses.create_category(user=admin, name=category_name)
    expenses.record_expense(
        user=admin,
        category_id=category.id,
        description="Office supplies",
        amount=amount,
        method="cash",
        occurred_on=occurred_on,
    )
    return category.id


# ---------------------------------------------------------------------------
# Income vs Expense for a selected month
# ---------------------------------------------------------------------------


def test_income_vs_expense_sums_the_selected_month(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "40.00", admin, paid_on=date(2026, 3, 10))
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 3, 12))

    report = reports.income_vs_expense(3, 2026)

    assert report.period_label == "March 2026"
    assert report.income_cents == 4000
    assert report.expenses_cents == 2500
    assert report.net_cents == 1500


def test_income_vs_expense_ignores_other_months(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "40.00", admin, paid_on=date(2026, 3, 10))
    pay(payments, student_id, "20.00", admin, paid_on=date(2026, 4, 2))
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 4, 5))

    report = reports.income_vs_expense(3, 2026)

    assert report.income_cents == 4000
    assert report.expenses_cents == 0
    assert report.net_cents == 4000


def test_income_vs_expense_breaks_down_by_method(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    payments.record_payment(
        user=admin, student_id=student_id, amount="30.00", method="cash", paid_on=date(2026, 3, 5)
    )
    payments.record_payment(
        user=admin, student_id=student_id, amount="20.00", method="bank", paid_on=date(2026, 3, 6)
    )
    category = expenses.create_category(user=admin, name="Salaries")
    expenses.record_expense(
        user=admin, category_id=category.id, description="Payroll", amount="10.00",
        method="cash", occurred_on=date(2026, 3, 7),
    )

    report = reports.income_vs_expense(3, 2026)

    income_methods = {line.method: line for line in report.income_by_method}
    assert income_methods[PaymentMethods.CASH].amount_cents == 3000
    assert income_methods[PaymentMethods.CASH].count == 1
    assert income_methods[PaymentMethods.BANK].amount_cents == 2000
    expense_methods = {line.method: line for line in report.expense_by_method}
    assert expense_methods[PaymentMethods.CASH].amount_cents == 1000
    assert report.income_cents == 5000
    assert report.expenses_cents == 1000


# ---------------------------------------------------------------------------
# Expense report by category
# ---------------------------------------------------------------------------


def test_expense_by_category_groups_and_orders_descending(
    reports, expenses, admin
):
    spend(expenses, "Utilities", "25.00", admin)
    spend(expenses, "Utilities", "15.00", admin)
    spend(expenses, "Salaries", "100.00", admin)

    report = reports.expense_by_category()

    assert [line.category_name for line in report.lines] == ["Salaries", "Utilities"]
    assert report.lines[0].total_cents == 10000
    assert report.lines[0].count == 1
    assert report.lines[1].total_cents == 4000
    assert report.lines[1].count == 2
    assert report.total_cents == 14000


def test_expense_by_category_filters_by_period(reports, expenses, admin):
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 3, 5))
    spend(expenses, "Salaries", "100.00", admin, occurred_on=date(2026, 4, 5))

    report = reports.expense_by_category(month=3, year=2026)

    assert [line.category_name for line in report.lines] == ["Utilities"]
    assert report.total_cents == 2500
    assert report.month == 3
    assert report.year == 2026
    assert report.period_label == "March 2026"


def test_expense_by_category_period_label_is_none_for_all_time(
    reports, expenses, admin
):
    spend(expenses, "Utilities", "25.00", admin)

    report = reports.expense_by_category()

    assert report.month is None
    assert report.year is None
    assert report.period_label is None


def test_expense_by_category_keeps_archived_categories(reports, expenses, admin):
    category_id = spend(expenses, "Utilities", "25.00", admin)
    expenses.remove_category(user=admin, category_id=category_id)

    report = reports.expense_by_category()

    assert [line.category_name for line in report.lines] == ["Utilities"]
    assert report.lines[0].total_cents == 2500


# ---------------------------------------------------------------------------
# Month dropdown periods
# ---------------------------------------------------------------------------


def test_list_periods_includes_billed_but_unpaid_months(
    reports, classes, students, fees, admin
):
    _, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)

    assert (2026, 3) in reports.list_periods()


def test_list_periods_covers_charges_payments_and_expenses(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "40.00", admin, paid_on=date(2026, 4, 2))
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 5, 5))

    assert reports.list_periods() == [(2026, 5), (2026, 4), (2026, 3)]


def test_list_periods_is_empty_with_no_data(reports):
    assert reports.list_periods() == []


# ---------------------------------------------------------------------------
# Paid students for a month (and by extension unpaid)
# ---------------------------------------------------------------------------


def test_paid_students_statuses_and_amounts(
    reports, payments, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "30.00", admin)

    report = reports.paid_students(3, 2026)

    (line,) = report.lines
    assert line.student.id == student_id
    assert line.class_name == "Grade 1"
    assert line.charge_cents == 5000
    assert line.paid_cents == 3000
    assert line.remaining_cents == 2000
    assert line.status == PaidStatus.PARTIAL


def test_paid_students_marks_fully_paid_and_unpaid(
    reports, payments, classes, students, fees, admin
):
    paid_id, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    unpaid_id, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)
    bill(fees, class_b, month=3, admin=admin)
    pay(payments, paid_id, "50.00", admin)

    report = reports.paid_students(3, 2026)

    by_student = {line.student.id: line for line in report.lines}
    assert by_student[paid_id].status == PaidStatus.PAID
    assert by_student[paid_id].remaining_cents == 0
    assert by_student[unpaid_id].status == PaidStatus.UNPAID
    assert by_student[unpaid_id].paid_cents == 0


def test_paid_students_only_includes_billed_students(
    reports, classes, students, fees, admin
):
    # A student in a class that was not generated for March must not appear.
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)

    report = reports.paid_students(3, 2026)

    assert [line.class_name for line in report.lines] == ["Grade 1"]


def test_paid_students_filters_by_class(
    reports, classes, students, fees, admin
):
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    _, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)
    bill(fees, class_b, month=3, admin=admin)

    report = reports.paid_students(3, 2026, class_id=class_a)

    assert report.class_name == "Grade 1"
    assert [line.class_name for line in report.lines] == ["Grade 1"]


def test_paid_students_totals_and_counts(
    reports, payments, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "20.00", admin)

    report = reports.paid_students(3, 2026)

    assert report.billed_count == 1
    assert report.paid_count == 0
    assert report.partial_count == 1
    assert report.unpaid_count == 0
    assert report.charged_cents == 5000
    assert report.collected_cents == 2000
    assert report.outstanding_cents == 3000


def test_paid_students_includes_archived_students(
    reports, students, classes, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    students.archive_student(user=admin, student_id=student_id)

    report = reports.paid_students(3, 2026)

    (line,) = report.lines
    assert line.student_status == StudentStatus.INACTIVE
    assert line.status == PaidStatus.UNPAID


def test_paid_students_reflects_waivers_and_extras(
    reports, adjustments, classes, students, fees, admin, session
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    charge = session.query(Charge).filter_by(student_id=student_id).one()
    adjustments.apply_waiver(user=admin, charge_id=charge.id, label="Scholarship", amount="10.00")

    report = reports.paid_students(3, 2026)

    (line,) = report.lines
    assert line.charge_cents == 4000
    assert line.remaining_cents == 4000


# ---------------------------------------------------------------------------
# Student status rows for a month (the /students page paid column)
# ---------------------------------------------------------------------------


def test_billed_periods_lists_only_charged_months_newest_first(
    reports, classes, students, fees, admin
):
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    _, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)
    bill(fees, class_b, month=5, admin=admin)

    assert reports.billed_periods() == [(2026, 5), (2026, 3)]


def test_billed_periods_is_empty_before_any_billing(reports):
    assert reports.billed_periods() == []


def test_student_status_rows_marks_paid_partial_and_unpaid(
    reports, payments, classes, students, fees, admin
):
    paid_id, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    partial_id, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    unpaid_id, class_c = make_class(
        classes, students, fees, admin, name="Grade 3", first_name="Alan", last_name="Turing"
    )
    bill(fees, class_a, month=3, admin=admin)
    bill(fees, class_b, month=3, admin=admin)
    bill(fees, class_c, month=3, admin=admin)
    pay(payments, paid_id, "50.00", admin)
    pay(payments, partial_id, "20.00", admin)

    all_students = students.search_students("")
    rows = reports.student_status_rows(all_students, 3, 2026)

    by_id = {row.student.id: row for row in rows}
    assert by_id[paid_id].paid_status == PaidStatus.PAID
    assert by_id[paid_id].remaining_cents == 0
    assert by_id[partial_id].paid_status == PaidStatus.PARTIAL
    assert by_id[partial_id].remaining_cents == 3000
    assert by_id[unpaid_id].paid_status == PaidStatus.UNPAID
    assert by_id[unpaid_id].remaining_cents == 5000


def test_student_status_rows_never_billed_students_have_no_status(
    reports, classes, students, fees, admin
):
    billed_id, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)

    rows = reports.student_status_rows(students.search_students(""), 3, 2026)

    by_id = {row.student.id: row for row in rows}
    assert by_id[billed_id].paid_status == PaidStatus.UNPAID
    assert all(
        row.paid_status is None and row.remaining_cents == 0
        for row in rows
        if row.student.id != billed_id
    )


def test_student_status_rows_status_filter_drops_never_billed(
    reports, classes, students, fees, admin
):
    billed_id, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    bill(fees, class_a, month=3, admin=admin)

    rows = reports.student_status_rows(students.search_students(""), 3, 2026, status=PaidStatus.UNPAID)

    assert [row.student.id for row in rows] == [billed_id]
    assert rows[0].paid_status == PaidStatus.UNPAID


def test_student_status_rows_other_months_leave_everyone_statusless(
    reports, classes, students, fees, admin
):
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    bill(fees, class_a, month=3, admin=admin)

    rows = reports.student_status_rows(students.search_students(""), 4, 2026)

    assert [row.paid_status for row in rows] == [None]


def test_student_status_rows_empty_student_list_is_empty(reports, classes, students, fees, admin):
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    bill(fees, class_a, month=3, admin=admin)

    assert reports.student_status_rows([], 3, 2026) == []


# ---------------------------------------------------------------------------
# Summarized finance report
# ---------------------------------------------------------------------------


def test_finance_summary_totals_income_expenses_arrears_credits(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)
    pay(payments, student_id, "60.00", admin, paid_on=date(2026, 3, 10))  # 50 paid, 10 credit
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 3, 12))

    summary = reports.finance_summary(3, 2026)

    assert summary.period_label == "March 2026"
    assert summary.income_cents == 6000
    assert summary.expenses_cents == 2500
    assert summary.net_cents == 3500
    assert summary.credits_cents == 1000
    assert summary.arrears_cents == 0  # fully paid, with 10 credit left over
    assert {row.label: row.amount_cents for row in summary.rows}["Net cash flow"] == 3500


def test_finance_summary_arrears_are_live_totals(
    reports, classes, students, fees, admin
):
    _, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=3, admin=admin)

    summary = reports.finance_summary(3, 2026)

    assert summary.arrears_cents == 5000


# ---------------------------------------------------------------------------
# Student list report
# ---------------------------------------------------------------------------


def test_student_list_lists_all_students_with_class_and_fee(
    reports, classes, students, fees, admin
):
    student_id, class_id = make_class(
        classes, students, fees, admin, items=(("Tuition", "50.00"), ("Boarding", "100.00"))
    )
    students.add_student(user=admin, class_id=class_id, first_name="Grace", last_name="Hopper")

    report = reports.student_list()

    assert report.class_name is None
    assert [line.student.full_name for line in report.lines] == [
        "Grace Hopper",
        "Ada Lovelace",
    ]
    assert all(line.monthly_fee_cents == 15000 for line in report.lines)
    assert report.active_count == 2
    assert report.inactive_count == 0


def test_student_list_includes_archived_students(reports, students, classes, fees, admin):
    student_id, class_id = make_class(classes, students, fees, admin)
    students.add_student(user=admin, class_id=class_id, first_name="Grace", last_name="Hopper")
    students.archive_student(user=admin, student_id=student_id)

    report = reports.student_list()

    by_name = {line.student.full_name: line for line in report.lines}
    assert by_name["Ada Lovelace"].student_status == StudentStatus.INACTIVE
    assert by_name["Grace Hopper"].student_status == StudentStatus.ACTIVE
    assert report.active_count == 1
    assert report.inactive_count == 1


def test_student_list_filters_by_class(reports, classes, students, fees, admin):
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    _, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )

    report = reports.student_list(class_id=class_a)

    assert report.class_name == "Grade 1"
    assert [line.class_name for line in report.lines] == ["Grade 1"]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_kpis_and_recent_activity(
    reports, payments, expenses, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=8, admin=admin)
    pay(payments, student_id, "30.00", admin, paid_on=date(2026, 8, 6))
    spend(expenses, "Utilities", "25.00", admin, occurred_on=date(2026, 8, 6))

    data = reports.dashboard(today=date(2026, 8, 6))

    assert data.month == 8
    assert data.year == 2026
    assert data.collected_cents == 3000
    assert data.expenses_cents == 2500
    assert data.arrears_cents == 2000  # 50.00 charge minus 30.00 paid
    assert data.active_student_count == 1
    assert len(data.recent_payments) == 1
    assert data.recent_payments[0].student.full_name == "Ada Lovelace"
    assert len(data.recent_expenses) == 1


def test_dashboard_monthly_series_spans_last_six_months(
    reports, payments, classes, students, fees, admin
):
    student_id, class_id = make_class(classes, students, fees, admin)
    bill(fees, class_id, month=4, admin=admin)
    pay(payments, student_id, "50.00", admin, paid_on=date(2026, 4, 6))

    data = reports.dashboard(today=date(2026, 8, 6))

    labels = [(line.month, line.year) for line in data.monthly]
    assert labels == [
        (3, 2026),
        (4, 2026),
        (5, 2026),
        (6, 2026),
        (7, 2026),
        (8, 2026),
    ]
    by_period = {(line.month, line.year): line for line in data.monthly}
    assert by_period[(4, 2026)].income_cents == 5000
    assert by_period[(8, 2026)].income_cents == 0


def test_dashboard_arrears_band_counts(
    reports, classes, students, fees, admin
):
    # A March debt (overdue), a July debt (late), and an August debt (current).
    _, class_a = make_class(classes, students, fees, admin, name="Grade 1")
    _, class_b = make_class(
        classes, students, fees, admin, name="Grade 2", first_name="Grace", last_name="Hopper"
    )
    _, class_c = make_class(
        classes, students, fees, admin, name="Grade 3", first_name="Katherine", last_name="Johnson"
    )
    bill(fees, class_a, month=3, admin=admin)
    bill(fees, class_b, month=7, admin=admin)
    bill(fees, class_c, month=8, admin=admin)

    data = reports.dashboard(today=date(2026, 8, 6))

    assert data.arrears_band_counts == {
        "current": 1,
        "late": 1,
        "overdue": 1,
    }
    assert data.arrears_cents == 15000


def test_dashboard_category_lines_feed_the_expense_chart(reports, expenses, admin):
    spend(expenses, "Utilities", "25.00", admin)
    spend(expenses, "Salaries", "100.00", admin)

    data = reports.dashboard(today=date(2026, 8, 6))

    assert [line.category_name for line in data.category_lines] == ["Salaries", "Utilities"]

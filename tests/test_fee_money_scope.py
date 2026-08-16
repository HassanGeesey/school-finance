"""Fee & money-flow scoping (multi-school 04).

Service-level tests with a seeded scope, following ticket 03's pattern: the
request scope resolves from the acting user and filters reads and stamps writes
on fee templates, closed months, expense categories, waivers, payments/credits,
and expenses. Two Campuses of one School each hold their own policy and money
rows; every row carries a Campus (ticket 09). Cross-campus ids are refused or
return empty, never data. Route concerns live in ``test_fee_money_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditService
from app.classes.service import ClassService
from app.expenses.service import (
    CategoryNotFound,
    ExpenseService,
)
from app.fees.service import (
    ClosedMonthError,
    ClosedMonthService,
    DuplicateClosedMonth,
    TemplateNotFound,
    TemplateService,
    WaiverError,
    WaiverService,
)
from app.models import (
    Class,
    ClosedMonth,
    Credit,
    Expense,
    ExpenseCategory,
    FeeTemplate,
    Payment,
    Student,
    StudentAmountChange,
    Waiver,
)
from app.payments.service import PaymentNotFound, PaymentService
from app.students.service import StudentNotFound, StudentService
from app.tenants.scope import RequestScope, scope_context
from tests.test_tenant_scope import seed_tenant_world

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def templates(db, audit) -> TemplateService:
    return TemplateService(db, audit=audit)


@pytest.fixture()
def closed_months(db, audit) -> ClosedMonthService:
    return ClosedMonthService(db, audit=audit)


@pytest.fixture()
def waivers(db, audit) -> WaiverService:
    return WaiverService(db, audit=audit)


@pytest.fixture()
def classes(db, audit) -> ClassService:
    return ClassService(db, audit=audit)


@pytest.fixture()
def students(db, audit) -> StudentService:
    return StudentService(db, audit=audit)


@pytest.fixture()
def payments(db, audit) -> PaymentService:
    return PaymentService(db, audit=audit)


@pytest.fixture()
def expenses(db, audit) -> ExpenseService:
    return ExpenseService(db, audit=audit)


def seed_fee_world(session, campus_a, campus_b):
    """A template + class + student per campus.

    Students are linked to their campus's template and enroll today (the model
    default), so the current month is their only owed month.
    """
    class_a = Class(name="Grade A", campus_id=campus_a.id)
    class_b = Class(name="Grade B", campus_id=campus_b.id)
    session.add_all([class_a, class_b])
    session.flush()
    template_a = FeeTemplate(name="Standard A", amount_cents=10000, campus_id=campus_a.id)
    template_b = FeeTemplate(name="Standard B", amount_cents=10000, campus_id=campus_b.id)
    session.add_all([template_a, template_b])
    session.flush()
    student_a = Student(
        class_id=class_a.id,
        campus_id=campus_a.id,
        first_name="Ada",
        last_name="Lovelace",
        fee_template_id=template_a.id,
    )
    student_b = Student(
        class_id=class_b.id,
        campus_id=campus_b.id,
        first_name="Grace",
        last_name="Hopper",
        fee_template_id=template_b.id,
    )
    session.add_all([student_a, student_b])
    session.commit()
    return (
        template_a,
        template_b,
        class_a,
        class_b,
        student_a,
        student_b,
    )


# ---------------------------------------------------------------------------
# Fee templates
# ---------------------------------------------------------------------------


def test_campus_admin_lists_only_own_campus_templates(templates, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    template_a, template_b, *_ = seed_fee_world(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        rows = templates.list_templates()

    assert {row.id for row in rows} == {template_a.id}
    assert template_b.id not in {row.id for row in rows}


def test_create_template_stamps_the_acting_campus(templates, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        template = templates.create_template(user=admin_a, name="Standard", amount="100.00")

    row = session.query(FeeTemplate).filter_by(id=template.id).one()
    assert row.campus_id == campus_a.id


def test_a_template_of_another_campus_is_invisible(templates, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    _template_a, template_b, *_ = seed_fee_world(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(TemplateNotFound):
            templates.get_template(template_b.id)
        with pytest.raises(TemplateNotFound):
            templates.update_template(
                user=admin_a,
                template_id=template_b.id,
                name="Hijacked",
                amount="100.00",
            )
        with pytest.raises(TemplateNotFound):
            templates.archive_template(user=admin_a, template_id=template_b.id)
        with pytest.raises(TemplateNotFound):
            templates.restore_template(user=admin_a, template_id=template_b.id)


def test_amount_change_propagates_only_to_own_campus_linked_students(
    templates, session
):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    template_a, _template_b, _class_a, _class_b, student_a, student_b = (
        seed_fee_world(session, campus_a, campus_b)
    )
    # A Campus-B student corruptly linked to A's template: propagation must not
    # reach across campuses, even though the linkage row exists.
    student_b.fee_template_id = template_a.id
    session.commit()
    today = date.today()
    month, year = (today.month % 12) + 1, today.year + (1 if today.month == 12 else 0)

    with scope_context(RequestScope.for_user(admin_a)):
        templates.update_template(
            user=admin_a,
            template_id=template_a.id,
            name="Standard A",
            amount="120.00",
            month=month,
            year=year,
        )

    changes = session.query(StudentAmountChange).all()
    assert all(c.student_id == student_a.id for c in changes)
    assert student_b.id not in [c.student_id for c in changes]


# ---------------------------------------------------------------------------
# Closed months
# ---------------------------------------------------------------------------


def test_add_closed_month_stamps_the_acting_campus(closed_months, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        closed_months.add_closed_month(user=admin_a, month=7, year=2026)

    row = session.query(ClosedMonth).one()
    assert (row.month, row.year) == (7, 2026)
    assert row.campus_id == campus_a.id


def test_closed_months_are_per_campus(closed_months, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        closed_months.add_closed_month(user=admin_a, month=7, year=2026)
        with pytest.raises(DuplicateClosedMonth):
            closed_months.add_closed_month(user=admin_a, month=7, year=2026)

    with scope_context(RequestScope.for_user(admin_b)):
        closed_months.add_closed_month(user=admin_b, month=7, year=2026)

    assert session.query(ClosedMonth).count() == 2
    assert {row.campus_id for row in session.query(ClosedMonth).all()} == {
        campus_a.id,
        campus_b.id,
    }


def test_closed_months_are_visible_only_in_scope(closed_months, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_a)):
        closed_months.add_closed_month(user=admin_a, month=7, year=2026)
    with scope_context(RequestScope.for_user(admin_b)):
        closed_months.add_closed_month(user=admin_b, month=8, year=2026)

    with scope_context(RequestScope.for_user(admin_a)):
        visible_a = {row.month for row in closed_months.list_closed_months()}
    with scope_context(RequestScope.for_user(admin_b)):
        visible_b = {row.month for row in closed_months.list_closed_months()}

    assert visible_a == {7}
    assert visible_b == {8}


def test_remove_closed_month_refuses_another_campuses_month(closed_months, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_b)):
        closed_months.add_closed_month(user=admin_b, month=8, year=2026)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ClosedMonthError):
            closed_months.remove_closed_month(user=admin_a, month=8, year=2026)


# ---------------------------------------------------------------------------
# Expense categories
# ---------------------------------------------------------------------------


def test_create_category_stamps_the_acting_campus(expenses, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        category = expenses.create_category(user=admin_a, name="Salaries")

    row = session.query(ExpenseCategory).filter_by(id=category.id).one()
    assert row.campus_id == campus_a.id


def test_both_campuses_may_reuse_the_same_category_name(expenses, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        expenses.create_category(user=admin_a, name="Salaries")
    with scope_context(RequestScope.for_user(admin_b)):
        expenses.create_category(user=admin_b, name="Salaries")

    assert session.query(ExpenseCategory).count() == 2
    with scope_context(RequestScope.for_user(admin_a)):
        assert [c.name for c in expenses.list_categories()] == ["Salaries"]
    with scope_context(RequestScope.for_user(admin_b)):
        assert [c.name for c in expenses.list_categories()] == ["Salaries"]


def test_a_category_of_another_campus_is_invisible(expenses, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_b)):
        category_b = expenses.create_category(user=admin_b, name="Transport")

    with scope_context(RequestScope.for_user(admin_a)):
        assert expenses.list_categories() == []
        with pytest.raises(CategoryNotFound):
            expenses.rename_category(
                user=admin_a, category_id=category_b.id, name="Haulage"
            )
        with pytest.raises(CategoryNotFound):
            expenses.remove_category(user=admin_a, category_id=category_b.id)


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------


def test_waiver_stamps_the_acting_campus(waivers, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    *_, student_a, _student_b = seed_fee_world(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        waivers.add_waiver(
            user=admin_a,
            student_id=student_a.id,
            month=6,
            year=2026,
            amount="10.00",
            label="Hardship",
        )

    row = session.query(Waiver).one()
    assert row.student_id == student_a.id
    assert row.campus_id == campus_a.id


def test_waiver_on_a_foreign_campus_student_is_refused(waivers, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    *_, _student_a, student_b = seed_fee_world(session, campus_a, campus_b)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(WaiverError):
            waivers.add_waiver(
                user=admin_a,
                student_id=student_b.id,
                month=6,
                year=2026,
                amount="10.00",
                label="Hardship",
            )


# ---------------------------------------------------------------------------
# Payments & credits
# ---------------------------------------------------------------------------


def test_payment_stamps_the_acting_campus(payments, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    *_, student_a, _student_b = seed_fee_world(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        payments.record_payment(
            user=admin_a,
            student_id=student_a.id,
            amount="120.00",
            method="cash",
            paid_on=today.isoformat(),
            month=today.month,
            year=today.year,
        )

    payment = session.query(Payment).one()
    assert payment.campus_id == campus_a.id
    credit = session.query(Credit).one()
    assert credit.campus_id == campus_a.id
    assert credit.payment_id == payment.id


def test_a_payment_on_a_foreign_campus_student_is_refused(payments, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    *_, _student_a, student_b = seed_fee_world(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(StudentNotFound):
            payments.record_payment(
                user=admin_a,
                student_id=student_b.id,
                amount="50.00",
                method="cash",
                paid_on=today.isoformat(),
                month=today.month,
                year=today.year,
            )
        with pytest.raises(StudentNotFound):
            payments.account_summary(student_b.id)


def test_get_payment_of_another_campus_raises(payments, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    *_, _student_a, student_b = seed_fee_world(session, campus_a, campus_b)
    today = date.today()
    with scope_context(RequestScope.for_user(admin_b)):
        payment_b = payments.record_payment(
            user=admin_b,
            student_id=student_b.id,
            amount="50.00",
            method="cash",
            paid_on=today.isoformat(),
            month=today.month,
            year=today.year,
        )

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(PaymentNotFound):
            payments.get_payment(payment_b.id)


def test_list_recent_payments_shows_only_own_campus(payments, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    *_, student_a, student_b = seed_fee_world(session, campus_a, campus_b)
    today = date.today()
    with scope_context(RequestScope.for_user(admin_a)):
        payments.record_payment(
            user=admin_a,
            student_id=student_a.id,
            amount="50.00",
            method="cash",
            paid_on=today.isoformat(),
            month=today.month,
            year=today.year,
        )
    with scope_context(RequestScope.for_user(admin_b)):
        payments.record_payment(
            user=admin_b,
            student_id=student_b.id,
            amount="50.00",
            method="cash",
            paid_on=today.isoformat(),
            month=today.month,
            year=today.year,
        )

    with scope_context(RequestScope.for_user(admin_a)):
        assert len(payments.list_recent_payments()) == 1
    with scope_context(RequestScope.for_user(superadmin)):
        assert len(payments.list_recent_payments()) == 2


def test_closed_months_are_per_campus_for_the_account_view(payments, closed_months, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    *_, student_a, student_b = seed_fee_world(session, campus_a, campus_b)
    today = date.today()

    with scope_context(RequestScope.for_user(admin_a)):
        closed_months.add_closed_month(user=admin_a, month=today.month, year=today.year)
        account_a = payments.account_summary(student_a.id).account

    with scope_context(RequestScope.for_user(admin_b)):
        account_b = payments.account_summary(student_b.id).account

    assert account_a.expected_cents == 0  # the only owed month is closed on Campus A
    assert account_b.expected_cents == 10000  # Campus B still owes its month


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


def test_expense_stamps_the_acting_campus(expenses, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_a)):
        category = expenses.create_category(user=admin_a, name="Supplies")
        expense = expenses.record_expense(
            user=admin_a,
            category_id=category.id,
            description="Chalk",
            amount="10.00",
            method="cash",
            occurred_on=date(2026, 8, 6),
        )

    row = session.query(Expense).filter_by(id=expense.id).one()
    assert row.campus_id == campus_a.id
    assert row.category_id == category.id


def test_an_expense_on_a_foreign_campus_category_is_refused(expenses, session):
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_b)):
        category_b = expenses.create_category(user=admin_b, name="Supplies")

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(CategoryNotFound):
            expenses.record_expense(
                user=admin_a,
                category_id=category_b.id,
                description="Chalk",
                amount="10.00",
                method="cash",
                occurred_on=date(2026, 8, 6),
            )


def test_expenses_and_periods_are_scoped(expenses, session):
    _school, campus_a, campus_b, admin_a, admin_b, superadmin = seed_tenant_world(session)
    with scope_context(RequestScope.for_user(admin_a)):
        category_a = expenses.create_category(user=admin_a, name="Supplies")
        expenses.record_expense(
            user=admin_a,
            category_id=category_a.id,
            description="Chalk",
            amount="10.00",
            method="cash",
            occurred_on=date(2026, 8, 6),
        )
    with scope_context(RequestScope.for_user(admin_b)):
        category_b = expenses.create_category(user=admin_b, name="Transport")
        expenses.record_expense(
            user=admin_b,
            category_id=category_b.id,
            description="Van fuel",
            amount="20.00",
            method="bank",
            occurred_on=date(2026, 8, 7),
        )

    with scope_context(RequestScope.for_user(admin_a)):
        listed = expenses.list_expenses()
        assert len(listed) == 1
        assert listed[0].description == "Chalk"
        assert expenses.list_periods() == [(2026, 8)]
    with scope_context(RequestScope.for_user(superadmin)):
        assert len(expenses.list_expenses()) == 2

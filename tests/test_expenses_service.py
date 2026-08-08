"""Expenses & categories service: recording money out, category management.

Business rules only — the single testing seam. The Admin manages an expense
category list (add/rename/archive) and Finance records expenses (date, category,
description, amount, method) against an existing, active category. Categories are
never hard-deleted — removing one archives it, so history keeps its label. Every
category change and every expense is audited. Route concerns live in
``test_expenses_routes.py``.
"""

from datetime import date

import pytest

from app.audit.service import AuditActions, AuditError, AuditService
from app.expenses.service import (
    CategoryNotFound,
    DuplicateCategoryName,
    ExpenseError,
    ExpenseService,
)
from app.models import AuditLogEntry, Expense, ExpenseCategory, User, UserRoles

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def audit(db) -> AuditService:
    return AuditService(db)


@pytest.fixture()
def expenses(db, audit) -> ExpenseService:
    return ExpenseService(db, audit=audit)


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


def categories(session) -> list[ExpenseCategory]:
    return (
        session.query(ExpenseCategory)
        .order_by(ExpenseCategory.id)
        .all()
    )


def expenses_rows(session) -> list[Expense]:
    return (
        session.query(Expense)
        .order_by(Expense.id)
        .all()
    )


def entries(session, action) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=action)
        .order_by(AuditLogEntry.id)
        .all()
    )


# ---------------------------------------------------------------------------
# Category management
# ---------------------------------------------------------------------------


def test_create_category_makes_it_listable(expenses, admin, session):
    created = expenses.create_category(user=admin, name="Utilities")

    assert created.name == "Utilities"
    assert created.is_active is True
    assert [c.name for c in expenses.list_categories()] == ["Utilities"]


def test_a_category_name_is_required(expenses, admin):
    with pytest.raises(ExpenseError):
        expenses.create_category(user=admin, name="  ")
    with pytest.raises(ExpenseError):
        expenses.create_category(user=admin, name="")


def test_a_category_name_is_trimmed(expenses, admin, session):
    created = expenses.create_category(user=admin, name="  Salaries  ")

    assert created.name == "Salaries"


def test_duplicate_category_names_are_rejected(expenses, admin):
    expenses.create_category(user=admin, name="Utilities")

    with pytest.raises(DuplicateCategoryName):
        expenses.create_category(user=admin, name="Utilities")


def test_duplicate_category_names_are_rejected_case_insensitively(expenses, admin):
    expenses.create_category(user=admin, name="Utilities")

    with pytest.raises(DuplicateCategoryName):
        expenses.create_category(user=admin, name="utilities")


def test_rename_category_updates_the_name(expenses, admin, session):
    created = expenses.create_category(user=admin, name="Utilities")

    renamed = expenses.rename_category(user=admin, category_id=created.id, name="Water & Power")

    assert renamed.name == "Water & Power"
    assert session.get(ExpenseCategory, created.id).name == "Water & Power"


def test_rename_to_an_existing_name_is_rejected(expenses, admin):
    utilities = expenses.create_category(user=admin, name="Utilities")
    expenses.create_category(user=admin, name="Salaries")

    with pytest.raises(DuplicateCategoryName):
        expenses.rename_category(user=admin, category_id=utilities.id, name="salaries")


def test_rename_requires_a_name(expenses, admin):
    created = expenses.create_category(user=admin, name="Utilities")

    with pytest.raises(ExpenseError):
        expenses.rename_category(user=admin, category_id=created.id, name="")


def test_rename_a_missing_category_raises(expenses, admin):
    with pytest.raises(CategoryNotFound):
        expenses.rename_category(user=admin, category_id=999, name="Utilities")


def test_remove_category_archives_it_and_hides_it_from_the_list(expenses, admin, session):
    created = expenses.create_category(user=admin, name="Transport")

    expenses.remove_category(user=admin, category_id=created.id)

    assert expenses.list_categories() == []
    archived = session.get(ExpenseCategory, created.id)
    assert archived is not None
    assert archived.is_active is False
    assert [c.name for c in expenses.list_categories(include_archived=True)] == ["Transport"]


def test_remove_a_missing_category_raises(expenses, admin):
    with pytest.raises(CategoryNotFound):
        expenses.remove_category(user=admin, category_id=999)


# ---------------------------------------------------------------------------
# Recording expenses
# ---------------------------------------------------------------------------


def test_record_expense_creates_a_row(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Supplies")

    expense = expenses.record_expense(
        user=admin,
        category_id=category.id,
        description="Chalk and pens",
        amount="45.50",
        method="cash",
        occurred_on=date(2026, 8, 6),
    )

    assert expense.category_id == category.id
    assert expense.description == "Chalk and pens"
    assert expense.amount_cents == 4550
    assert expense.method == "cash"
    assert expense.occurred_on == date(2026, 8, 6)
    assert expense.recorded_by == admin.id


def test_record_expense_can_happen_without_an_actor(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Supplies")

    expense = expenses.record_expense(
        user=None,
        category_id=category.id,
        description="Chalk",
        amount="10.00",
        method="bank",
        occurred_on=date(2026, 8, 6),
    )

    assert expense.recorded_by is None


def test_record_expense_requires_a_positive_amount(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="0", method="cash", occurred_on=date(2026, 8, 6),
        )
    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="-5.00", method="cash", occurred_on=date(2026, 8, 6),
        )
    assert expenses_rows(session) == []


def test_record_expense_rejects_a_bad_amount(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="not-money", method="cash", occurred_on=date(2026, 8, 6),
        )


def test_record_expense_translates_the_shared_amount_rule(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError, match="Enter a valid amount"):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="not-money", method="cash", occurred_on=date(2026, 8, 6),
        )
    with pytest.raises(ExpenseError, match="greater than zero"):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="0", method="cash", occurred_on=date(2026, 8, 6),
        )


def test_record_expense_rejects_an_unknown_method(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="10.00", method="cheque", occurred_on=date(2026, 8, 6),
        )


def test_record_expense_rejects_a_future_date(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="10.00", method="cash", occurred_on=date(2100, 1, 1),
        )


def test_record_expense_requires_a_description(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="  ",
            amount="10.00", method="cash", occurred_on=date(2026, 8, 6),
        )


def test_record_expense_rejects_a_missing_category(expenses, admin):
    with pytest.raises(CategoryNotFound):
        expenses.record_expense(
            user=admin, category_id=999, description="Chalk",
            amount="10.00", method="cash", occurred_on=date(2026, 8, 6),
        )


def test_record_expense_rejects_an_archived_category(expenses, admin):
    category = expenses.create_category(user=admin, name="Transport")
    expenses.remove_category(user=admin, category_id=category.id)

    with pytest.raises(CategoryNotFound):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Van fuel",
            amount="20.00", method="cash", occurred_on=date(2026, 8, 6),
        )


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def make_expenses(expenses, admin, category, amounts_and_dates):
    for amount, when in amounts_and_dates:
        expenses.record_expense(
            user=admin, category_id=category.id, description="Test spend",
            amount=amount, method="cash", occurred_on=when,
        )


def test_list_expenses_orders_most_recent_first(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")
    make_expenses(
        expenses, admin, category,
        [("10.00", date(2026, 8, 1)), ("20.00", date(2026, 8, 5)), ("30.00", date(2026, 7, 31))],
    )

    listed = expenses.list_expenses()

    assert [e.amount_cents for e in listed] == [2000, 1000, 3000]


def test_list_expenses_filters_by_category(expenses, admin):
    supplies = expenses.create_category(user=admin, name="Supplies")
    salaries = expenses.create_category(user=admin, name="Salaries")
    make_expenses(expenses, admin, supplies, [("10.00", date(2026, 8, 1))])
    make_expenses(expenses, admin, salaries, [("50.00", date(2026, 8, 2))])

    listed = expenses.list_expenses(category_id=salaries.id)

    assert [e.amount_cents for e in listed] == [5000]


def test_list_expenses_filters_by_month_and_year(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")
    make_expenses(
        expenses, admin, category,
        [("10.00", date(2026, 8, 1)), ("20.00", date(2026, 7, 15)), ("30.00", date(2025, 8, 20))],
    )

    listed = expenses.list_expenses(month=8, year=2026)

    assert [e.amount_cents for e in listed] == [1000]


def test_list_expenses_combines_filters(expenses, admin):
    supplies = expenses.create_category(user=admin, name="Supplies")
    salaries = expenses.create_category(user=admin, name="Salaries")
    make_expenses(expenses, admin, supplies, [("10.00", date(2026, 8, 1)), ("30.00", date(2026, 7, 1))])
    make_expenses(expenses, admin, salaries, [("50.00", date(2026, 8, 2))])

    listed = expenses.list_expenses(category_id=supplies.id, month=8, year=2026)

    assert [e.amount_cents for e in listed] == [1000]


def test_list_expenses_loads_its_category(expenses, admin):
    category = expenses.create_category(user=admin, name="Utilities")
    make_expenses(expenses, admin, category, [("10.00", date(2026, 8, 1))])

    (expense,) = expenses.list_expenses()

    assert expense.category.name == "Utilities"


def test_list_periods_returns_distinct_months_most_recent_first(expenses, admin):
    category = expenses.create_category(user=admin, name="Supplies")
    make_expenses(
        expenses, admin, category,
        [("10.00", date(2026, 8, 1)), ("20.00", date(2026, 8, 5)), ("30.00", date(2026, 7, 31))],
    )

    assert expenses.list_periods() == [(2026, 8), (2026, 7)]


def test_list_periods_is_empty_without_expenses(expenses):
    assert expenses.list_periods() == []


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_category_creation_is_audited(expenses, admin, session):
    expenses.create_category(user=admin, name="Salaries")

    (entry,) = entries(session, AuditActions.EXPENSE_CATEGORY_ADD)
    assert entry.user_id == admin.id
    assert "Salaries" in entry.summary


def test_category_rename_is_audited(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Salaries")

    expenses.rename_category(user=admin, category_id=category.id, name="Staff pay")

    (entry,) = entries(session, AuditActions.EXPENSE_CATEGORY_RENAME)
    assert entry.user_id == admin.id
    assert "Salaries" in entry.summary
    assert "Staff pay" in entry.summary


def test_category_removal_is_audited(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Transport")

    expenses.remove_category(user=admin, category_id=category.id)

    (entry,) = entries(session, AuditActions.EXPENSE_CATEGORY_REMOVE)
    assert entry.user_id == admin.id
    assert "Transport" in entry.summary


def test_an_expense_is_audited(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Supplies")

    expenses.record_expense(
        user=admin, category_id=category.id, description="Chalk",
        amount="45.50", method="bank", occurred_on=date(2026, 8, 6),
    )

    (entry,) = entries(session, AuditActions.EXPENSE_RECORD)
    assert entry.user_id == admin.id
    assert "Chalk" in entry.summary
    assert "$45.50" in entry.summary
    assert "Supplies" in entry.summary
    assert "Bank" in entry.summary
    assert "2026-08-06" in entry.summary


def test_a_rejected_expense_writes_no_audit_entry(expenses, admin, session):
    category = expenses.create_category(user=admin, name="Supplies")

    with pytest.raises(ExpenseError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="0", method="cash", occurred_on=date(2026, 8, 6),
        )

    assert entries(session, AuditActions.EXPENSE_RECORD) == []


def test_an_audit_failure_rolls_back_the_whole_expense(
    expenses, admin, session
):
    """The audit entry lands in the same transaction as the expense, so a
    failure to audit must undo the expense too — nothing is recorded that
    isn't also audited."""
    category = expenses.create_category(user=admin, name="Supplies")

    class BrokenAudit:
        def add(self, session, *, user, action, summary):
            raise AuditError("boom")

    expenses._audit = BrokenAudit()  # type: ignore[assignment]

    with pytest.raises(AuditError):
        expenses.record_expense(
            user=admin, category_id=category.id, description="Chalk",
            amount="10.00", method="cash", occurred_on=date(2026, 8, 6),
        )

    assert expenses_rows(session) == []
    assert entries(session, AuditActions.EXPENSE_RECORD) == []

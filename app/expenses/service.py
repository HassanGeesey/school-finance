"""Expenses & categories service layer.

Business rules for recording money out. The Admin manages an expense category
list (e.g. Salaries, Utilities, Supplies, Maintenance, Transport, Other) and
Finance records an expense (date, category, description, amount, method)
against an existing, active category. Routes are thin adapters over this module
— it is the single testing seam.

Rules that live here:
- Amounts are positive integer cents (``app.money``), never floats.
- The method is one of cash/bank/other (``PaymentMethods``).
- The expense date must parse and cannot be in the future.
- A category name is required and unique across categories, case-insensitively.
- There are no hard deletes: removing a category archives it (``is_active``
  becomes false). Archived categories stop appearing in the record dropdown but
  their expenses keep the category label on every historical row.
- An expense can only be recorded against an active category.
- Expenses are listed most recent first and can be filtered by category and/or
  month+year; ``list_periods`` feeds the month filter dropdown.
- Every category change and every expense writes one audit entry; a rejected
  expense writes nothing.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import Expense, ExpenseCategory, PaymentMethods, User
from ..tenants.scope import (
    campus_for_write,
    in_scope,
    scope,
    scoped_campus_filter,
)
from ..money import (
    InvalidAmount,
    Money,
    NonPositiveAmount,
    format_cents,
    parse_positive_cents,
)

EXPENSE_METHOD_LABELS = {
    PaymentMethods.CASH: "Cash",
    PaymentMethods.BANK: "Bank",
    PaymentMethods.OTHER: "Other",
}
VALID_EXPENSE_METHODS = set(EXPENSE_METHOD_LABELS)


class ExpenseError(Exception):
    """Rejected input or state in an expense operation."""


class CategoryNotFound(ExpenseError):
    """No (active) expense category exists with the given id."""


class DuplicateCategoryName(ExpenseError):
    """An expense category with that name already exists."""


class ExpenseService:
    """Expense business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _validate_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ExpenseError("A category name is required.")
        return cleaned

    @staticmethod
    def _validate_description(description: str) -> str:
        cleaned = (description or "").strip()
        if not cleaned:
            raise ExpenseError("A description is required.")
        return cleaned

    @staticmethod
    def _validate_amount(amount: object) -> int:
        try:
            return parse_positive_cents(amount)  # type: ignore[arg-type]
        except InvalidAmount:
            raise ExpenseError("Enter a valid amount.") from None
        except NonPositiveAmount:
            raise ExpenseError("Amount must be greater than zero.") from None

    @staticmethod
    def _validate_method(method: str) -> str:
        if method not in VALID_EXPENSE_METHODS:
            raise ExpenseError("Choose Cash, Bank, or Other.")
        return method

    @staticmethod
    def _validate_date(value: object) -> date:
        if isinstance(value, date):
            occurred_on = value
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                raise ExpenseError("Choose an expense date.")
            try:
                occurred_on = date.fromisoformat(raw)
            except ValueError:
                raise ExpenseError("Enter a valid expense date.") from None
        else:
            raise ExpenseError("Choose an expense date.")
        if occurred_on > date.today():
            raise ExpenseError("Expense date cannot be in the future.")
        return occurred_on

    @staticmethod
    def _get_category(
        session: Session, category_id: int, *, active_only: bool = False
    ) -> ExpenseCategory:
        query = session.query(ExpenseCategory)
        if active_only:
            query = query.filter(ExpenseCategory.is_active.is_(True))
        category = query.filter(ExpenseCategory.id == category_id).one_or_none()
        if category is None:
            suffix = " active" if active_only else ""
            raise CategoryNotFound(f"No{suffix} expense category with id {category_id} exists.")
        cur = scope()
        if cur is not None and not in_scope(session, cur, category.campus_id):
            suffix = " active" if active_only else ""
            raise CategoryNotFound(f"No{suffix} expense category with id {category_id} exists.")
        return category

    @staticmethod
    def _category_name_taken(
        session: Session, name: str, exclude_id: int | None = None
    ) -> bool:
        query = session.query(func.lower(ExpenseCategory.name)).filter(
            func.lower(ExpenseCategory.name) == name.lower()
        )
        cur = scope()
        if cur is not None:
            query = query.filter(
                scoped_campus_filter(session, cur, ExpenseCategory.campus_id)
            )
        if exclude_id is not None:
            query = query.filter(ExpenseCategory.id != exclude_id)
        return query.first() is not None

    # -- Categories ---------------------------------------------------------

    def list_categories(self, *, include_archived: bool = False) -> list[ExpenseCategory]:
        """Active categories alphabetically, or all of them when ``include_archived``."""
        with self._session() as session:
            query = session.query(ExpenseCategory)
            cur = scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, ExpenseCategory.campus_id)
                )
            if not include_archived:
                query = query.filter(ExpenseCategory.is_active.is_(True))
            return query.order_by(ExpenseCategory.name, ExpenseCategory.id).all()

    def create_category(self, *, user: User | None, name: str) -> ExpenseCategory:
        name = self._validate_name(name)

        with self._session() as session:
            if self._category_name_taken(session, name):
                raise DuplicateCategoryName(
                    f"An expense category named '{name}' already exists."
                )
            category = ExpenseCategory(
                name=name, campus_id=campus_for_write(scope())
            )
            session.add(category)
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateCategoryName(
                    f"An expense category named '{name}' already exists."
                ) from None
            session.refresh(category)
        self._log(
            user=user,
            action=AuditActions.EXPENSE_CATEGORY_ADD,
            summary=f"Added expense category {category.name}",
        )
        return category

    def rename_category(
        self, *, user: User | None, category_id: int, name: str
    ) -> ExpenseCategory:
        name = self._validate_name(name)

        with self._session() as session:
            category = self._get_category(session, category_id)
            if self._category_name_taken(session, name, exclude_id=category.id):
                raise DuplicateCategoryName(
                    f"An expense category named '{name}' already exists."
                )
            if category.name == name:
                return category
            old = category.name
            category.name = name
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateCategoryName(
                    f"An expense category named '{name}' already exists."
                ) from None
            session.refresh(category)
        self._log(
            user=user,
            action=AuditActions.EXPENSE_CATEGORY_RENAME,
            summary=f"Renamed expense category {old} to {name}",
        )
        return category

    def remove_category(self, *, user: User | None, category_id: int) -> None:
        """Archive a category: hidden from the record dropdown, history preserved."""
        with self._session() as session:
            category = self._get_category(session, category_id)
            name = category.name
            category.is_active = False
            session.commit()
        self._log(
            user=user,
            action=AuditActions.EXPENSE_CATEGORY_REMOVE,
            summary=f"Removed expense category {name}",
        )

    # -- Expenses -----------------------------------------------------------

    def record_expense(
        self,
        *,
        user: User | None,
        category_id: int,
        description: str,
        amount: object,
        method: str,
        occurred_on: object,
    ) -> Expense:
        """Record one expense against an active category, in one transaction.

        The expense and its audit entry land atomically — a rejected expense
        writes nothing.
        """
        description = self._validate_description(description)
        amount_cents = self._validate_amount(amount)
        method = self._validate_method(method)
        occurred_on = self._validate_date(occurred_on)

        with self._session() as session:
            category = self._get_category(session, category_id, active_only=True)
            expense = Expense(
                category_id=category.id,
                description=description,
                amount_cents=amount_cents,
                method=method,
                occurred_on=occurred_on,
                campus_id=campus_for_write(scope()),
                recorded_by=user.id if user is not None else None,
            )
            session.add(expense)
            if self._audit is not None:
                self._audit.add(
                    session,
                    user=user,
                    action=AuditActions.EXPENSE_RECORD,
                    summary=(
                        f"Recorded expense of {format_cents(amount_cents)} "
                        f"({category.name}) on {occurred_on.isoformat()}: "
                        f"{description} via {EXPENSE_METHOD_LABELS[method]}"
                    ),
                )
            session.commit()
            session.refresh(expense)
        return expense

    def list_expenses(
        self,
        *,
        category_id: int | None = None,
        month: int | None = None,
        year: int | None = None,
    ) -> list[Expense]:
        """Expenses most recent first, optionally filtered by category and month."""
        with self._session() as session:
            query = session.query(Expense).options(joinedload(Expense.category))
            cur = scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Expense.campus_id))
            if category_id is not None:
                query = query.filter(Expense.category_id == category_id)
            if month is not None and year is not None:
                first = date(year, month, 1)
                last = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
                query = query.filter(Expense.occurred_on >= first, Expense.occurred_on < last)
            return (
                query.order_by(Expense.occurred_on.desc(), Expense.id.desc()).all()
            )

    def list_periods(self) -> list[tuple[int, int]]:
        """Distinct (year, month) pairs in the expense log, most recent first.

        Feeds the month filter dropdown so it only offers months with data.
        """
        with self._session() as session:
            query = session.query(Expense.occurred_on)
            cur = scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Expense.campus_id))
            rows = query.distinct().all()
        periods = {(when.year, when.month) for (when,) in rows}
        return sorted(periods, reverse=True)

    def total_cents(
        self,
        *,
        category_id: int | None = None,
        month: int | None = None,
        year: int | None = None,
    ) -> Money:
        """Sum of the filtered expenses, for the list card total."""
        return sum(
            expense.amount_cents
            for expense in self.list_expenses(
                category_id=category_id, month=month, year=year
            )
        )

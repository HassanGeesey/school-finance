"""Reports service layer: report aggregations and the dashboard.

The reporting surface. This module is read-only — it aggregates payments,
expenses, charges, and arrears into the report surfaces and the dashboard
KPIs/charts. Routes are thin adapters over this module — it is the single
testing seam.

Rules that live here:
- Amounts stay in integer cents (``app.money``) throughout.
- Income for a month = all payments dated within it; expenses for a month =
  all expenses dated within it; net = income - expenses.
- Expense-by-category groups all expenses (or one month's) by category,
  largest total first; archived categories keep their historical rows.
- The paid-students report lists every student billed for the month (optionally
  one class): their live net charge (base + extras - waivers), what payments
  have cleared, and a paid/partial/unpaid status. Never-billed students do not
  appear; archived students keep their charges and do appear.
- The summarized finance report rolls up one month's income and expenses, the
  net, and the live totals for outstanding arrears and credit balances.
- The student list is the register: every student (optionally one class) with
  their class, status, and the class's current monthly fee.
- The dashboard is the current month's KPIs (collections, expenses, arrears,
  active students), a six-month income/expense series, the arrears debt-age
  band counts, and the all-time expense-by-category lines — the Chart.js
  payloads are assembled in the routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..arrears.service import ArrearsService
from ..classes.service import ClassNotFound
from ..db import Database
from ..fees.service import net_cents, period_label
from ..models import (
    Charge,
    Class,
    Credit,
    Expense,
    FeeItem,
    Payment,
    PaymentAllocation,
    Student,
    StudentStatus,
)
from ..money import Money
from ..payments.service import PAYMENT_METHOD_LABELS


class PaidStatus:
    PAID = "paid"
    PARTIAL = "partial"
    UNPAID = "unpaid"


PAID_STATUS_LABELS = {
    PaidStatus.PAID: "Paid",
    PaidStatus.PARTIAL: "Partial",
    PaidStatus.UNPAID: "Unpaid",
}

DASHBOARD_MONTHS = 6


@dataclass
class MethodLine:
    """One payment/expense method's contribution to a month's totals."""

    method: str
    label: str
    count: int
    amount_cents: Money


@dataclass
class PeriodLine:
    """One month in the dashboard's six-month income/expense series."""

    month: int
    year: int
    label: str
    income_cents: Money
    expenses_cents: Money
    net_cents: Money


@dataclass
class IncomeExpenseReport:
    """A month's money in (payments) vs money out (expenses)."""

    month: int
    year: int
    period_label: str
    income_cents: Money
    expenses_cents: Money
    net_cents: Money
    income_by_method: list[MethodLine]
    expense_by_method: list[MethodLine]


@dataclass
class CategoryLine:
    """One category's row in the expense-by-category report."""

    category_id: int
    category_name: str
    count: int
    total_cents: Money


@dataclass
class ExpenseCategoryReport:
    """Expenses grouped by category, optionally for one month."""

    month: int | None
    year: int | None
    period_label: str | None
    total_cents: Money
    lines: list[CategoryLine]


@dataclass
class PaidStudentLine:
    """One billed student's row in the paid-students report."""

    student: Student
    class_name: str
    class_status: str
    student_status: str
    charge_cents: Money
    paid_cents: Money
    remaining_cents: Money
    status: str


@dataclass
class PaidStudentsReport:
    """Who was billed for a month and whether they have paid."""

    month: int
    year: int
    period_label: str
    class_id: int | None
    class_name: str | None
    billed_count: int
    paid_count: int
    partial_count: int
    unpaid_count: int
    charged_cents: Money
    collected_cents: Money
    outstanding_cents: Money
    lines: list[PaidStudentLine]


@dataclass
class SummaryRow:
    """One row in the summarized finance table."""

    label: str
    amount_cents: Money


@dataclass
class FinanceSummary:
    """The summarized finance report: month totals + live balance figures."""

    month: int
    year: int
    period_label: str
    income_cents: Money
    expenses_cents: Money
    net_cents: Money
    arrears_cents: Money
    credits_cents: Money
    rows: list[SummaryRow]


@dataclass
class StudentListLine:
    """One student's row in the register export."""

    student: Student
    class_name: str
    class_status: str
    student_status: str
    monthly_fee_cents: Money


@dataclass
class StudentStatusRow:
    """One student on the school-wide search page, with their month's paid status.

    ``paid_status`` is one of :class:`PaidStatus` when the student was billed
    that month, else ``None`` (never billed — rendered as a dash). The rest of
    the paid column renders from the shared ``PAID_STATUS_LABELS`` / tones.
    """

    student: Student
    paid_status: str | None
    remaining_cents: Money


@dataclass
class StudentListReport:
    """The student register: every student (or one class) with class + fee."""

    class_id: int | None
    class_name: str | None
    active_count: int
    inactive_count: int
    lines: list[StudentListLine]


@dataclass
class DashboardData:
    """Everything the dashboard page needs: KPIs, charts, recent activity."""

    month: int
    year: int
    collected_cents: Money
    expenses_cents: Money
    arrears_cents: Money
    credits_cents: Money
    active_student_count: int
    recent_payments: list[Payment]
    recent_expenses: list[Expense]
    monthly: list[PeriodLine]
    arrears_band_counts: dict[str, int]
    category_lines: list[CategoryLine]


def _period_bounds(year: int, month: int) -> tuple[date, date]:
    """The half-open date range covering one calendar month."""
    first = date(year, month, 1)
    last = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, last


class ReportService:
    """Report aggregations. Read-only; each method is one unit of work.

    Needs an :class:`ArrearsService` (injected) for the figures that depend on
    live arrears — the dashboard and the summarized finance report.
    """

    def __init__(self, db: Database, arrears: ArrearsService) -> None:
        self._db = db
        self._arrears = arrears

    def _session(self) -> Session:
        return self._db.session()

    @staticmethod
    def _by_method(rows: list) -> list[MethodLine]:
        totals: dict[str, int] = {}
        counts: dict[str, int] = {}
        for row in rows:
            totals[row.method] = totals.get(row.method, 0) + row.amount_cents
            counts[row.method] = counts.get(row.method, 0) + 1
        return [
            MethodLine(
                method=method,
                label=label,
                count=counts[method],
                amount_cents=totals[method],
            )
            for method, label in PAYMENT_METHOD_LABELS.items()
            if method in totals
        ]

    @staticmethod
    def _amounts_by_month(
        rows: Iterable[tuple[date, int]],
    ) -> dict[tuple[int, int], int]:
        totals: dict[tuple[int, int], int] = {}
        for when, amount_cents in rows:
            key = (when.year, when.month)
            totals[key] = totals.get(key, 0) + amount_cents
        return totals

    def _payment_amounts_by_month(
        self, start: date | None = None
    ) -> dict[tuple[int, int], int]:
        with self._session() as session:
            query = session.query(Payment.paid_on, Payment.amount_cents)
            if start is not None:
                query = query.filter(Payment.paid_on >= start)
            rows = query.all()
        return self._amounts_by_month([(row[0], row[1]) for row in rows])

    def _expense_amounts_by_month(
        self, start: date | None = None
    ) -> dict[tuple[int, int], int]:
        with self._session() as session:
            query = session.query(Expense.occurred_on, Expense.amount_cents)
            if start is not None:
                query = query.filter(Expense.occurred_on >= start)
            rows = query.all()
        return self._amounts_by_month([(row[0], row[1]) for row in rows])

    def _credits_total(self) -> Money:
        with self._session() as session:
            total = session.query(func.coalesce(func.sum(Credit.amount_cents), 0)).scalar()
        return int(total or 0)

    def _active_student_count(self) -> int:
        with self._session() as session:
            return int(
                session.query(func.count(Student.id))
                .filter(Student.status == StudentStatus.ACTIVE)
                .scalar()
            )

    def _recent_payments(self, limit: int = 5) -> list[Payment]:
        with self._session() as session:
            return (
                session.query(Payment)
                .options(joinedload(Payment.student).joinedload(Student.school_class))
                .order_by(Payment.created_at.desc(), Payment.id.desc())
                .limit(limit)
                .all()
            )

    def _recent_expenses(self, limit: int = 5) -> list[Expense]:
        with self._session() as session:
            return (
                session.query(Expense)
                .options(joinedload(Expense.category))
                .order_by(Expense.created_at.desc(), Expense.id.desc())
                .limit(limit)
                .all()
            )

    def _arrears_lines(self, today: date) -> list:
        return self._arrears.arrears_report(today=today)

    def list_periods(self) -> list[tuple[int, int]]:
        """Every (year, month) with charges, payments, or expenses, newest first.

        Feeds the report month dropdowns. Charges are included so a month that
        was billed but collected nothing can still be selected — that is exactly
        what the paid-students report is for.
        """
        with self._session() as session:
            charge_rows = session.query(Charge.year, Charge.month).distinct().all()
            payment_rows = session.query(
                func.strftime("%Y", Payment.paid_on), func.strftime("%m", Payment.paid_on)
            ).distinct().all()
            expense_rows = session.query(
                func.strftime("%Y", Expense.occurred_on), func.strftime("%m", Expense.occurred_on)
            ).distinct().all()
        periods: set[tuple[int, int]] = set()
        for row in [*charge_rows, *payment_rows, *expense_rows]:
            periods.add((int(row[0]), int(row[1])))
        return sorted(periods, reverse=True)

    @staticmethod
    def _class_name(session: Session, class_id: int) -> str:
        cls = session.get(Class, class_id)
        if cls is None:
            raise ClassNotFound(f"No class with id {class_id} exists.")
        return cls.name

    @staticmethod
    def _classify_status(net: int, paid: int) -> tuple[str, int]:
        """The paid status and remaining cents for a charge net vs paid."""
        remaining = max(net - paid, 0)
        if remaining <= 0:
            return PaidStatus.PAID, remaining
        if paid > 0:
            return PaidStatus.PARTIAL, remaining
        return PaidStatus.UNPAID, remaining

    @staticmethod
    def _student_sort_key(
        line: PaidStudentLine | StudentListLine,
    ) -> tuple[str, str, str, int]:
        return (
            line.class_name,
            line.student.last_name,
            line.student.first_name,
            line.student.id,
        )

    # -- Income vs Expense ---------------------------------------------------

    def income_vs_expense(self, month: int, year: int) -> IncomeExpenseReport:
        """A month's income (payments) and expenses, and the net."""
        first, last = _period_bounds(year, month)
        with self._session() as session:
            payments = (
                session.query(Payment)
                .filter(Payment.paid_on >= first, Payment.paid_on < last)
                .all()
            )
            expenses = (
                session.query(Expense)
                .filter(Expense.occurred_on >= first, Expense.occurred_on < last)
                .all()
            )
        income_cents = sum(p.amount_cents for p in payments)
        expenses_cents = sum(e.amount_cents for e in expenses)
        return IncomeExpenseReport(
            month=month,
            year=year,
            period_label=period_label(month, year),
            income_cents=income_cents,
            expenses_cents=expenses_cents,
            net_cents=income_cents - expenses_cents,
            income_by_method=self._by_method(payments),
            expense_by_method=self._by_method(expenses),
        )

    # -- Expense by category -------------------------------------------------

    def expense_by_category(
        self, month: int | None = None, year: int | None = None
    ) -> ExpenseCategoryReport:
        """Expenses grouped by category, largest total first.

        Filter to one month when both ``month`` and ``year`` are given;
        otherwise every expense counts.
        """
        filtered = month is not None and year is not None
        with self._session() as session:
            query = session.query(Expense).options(joinedload(Expense.category))
            if filtered:
                first, last = _period_bounds(year, month)  # type: ignore[arg-type]
                query = query.filter(
                    Expense.occurred_on >= first, Expense.occurred_on < last
                )
            expenses = query.all()

        by_category: dict[int, CategoryLine] = {}
        for expense in expenses:
            line = by_category.setdefault(
                expense.category_id,
                CategoryLine(
                    category_id=expense.category_id,
                    category_name=expense.category.name,
                    count=0,
                    total_cents=0,
                ),
            )
            line.count += 1
            line.total_cents += expense.amount_cents
        lines = sorted(
            by_category.values(), key=lambda line: (-line.total_cents, line.category_name)
        )
        return ExpenseCategoryReport(
            month=month if filtered else None,
            year=year if filtered else None,
            period_label=period_label(month, year) if filtered else None,  # type: ignore[arg-type]
            total_cents=sum(line.total_cents for line in lines),
            lines=lines,
        )

    # -- Paid students for a month ------------------------------------------

    def paid_students(
        self,
        month: int,
        year: int,
        class_id: int | None = None,
    ) -> PaidStudentsReport:
        """Every student billed for the month, with their payment status.

        Students are included only when they hold a charge for that month;
        archived students keep theirs and still appear. Order is by class then
        student name.
        """
        with self._session() as session:
            class_name = (
                self._class_name(session, class_id) if class_id is not None else None
            )
            query = (
                session.query(Charge)
                .options(
                    joinedload(Charge.student).joinedload(Student.school_class),
                    joinedload(Charge.adjustments),
                )
                .filter(Charge.month == month, Charge.year == year)
            )
            if class_id is not None:
                query = query.filter(Charge.student.has(Student.class_id == class_id))
            charges = query.all()
            paid_by_charge = self._paid_cents_by_charge(
                session, [charge.id for charge in charges]
            )

        lines: list[PaidStudentLine] = []
        for charge in charges:
            student = charge.student
            net = net_cents(charge, list(charge.adjustments))
            paid = paid_by_charge.get(charge.id, 0)
            status, remaining = self._classify_status(net, paid)
            lines.append(
                PaidStudentLine(
                    student=student,
                    class_name=student.school_class.name,
                    class_status=student.school_class.status,
                    student_status=student.status,
                    charge_cents=net,
                    paid_cents=paid,
                    remaining_cents=remaining,
                    status=status,
                )
            )
        lines.sort(key=self._student_sort_key)
        charged_cents = sum(line.charge_cents for line in lines)
        collected_cents = sum(line.paid_cents for line in lines)
        return PaidStudentsReport(
            month=month,
            year=year,
            period_label=period_label(month, year),
            class_id=class_id,
            class_name=class_name,
            billed_count=len(lines),
            paid_count=sum(1 for line in lines if line.status == PaidStatus.PAID),
            partial_count=sum(1 for line in lines if line.status == PaidStatus.PARTIAL),
            unpaid_count=sum(1 for line in lines if line.status == PaidStatus.UNPAID),
            charged_cents=charged_cents,
            collected_cents=collected_cents,
            outstanding_cents=charged_cents - collected_cents,
            lines=lines,
        )

    @staticmethod
    def _paid_cents_by_charge(
        session: Session, charge_ids: list[int]
    ) -> dict[int, int]:
        if not charge_ids:
            return {}
        rows = (
            session.query(
                PaymentAllocation.charge_id,
                func.sum(PaymentAllocation.amount_cents),
            )
            .filter(PaymentAllocation.charge_id.in_(charge_ids))
            .group_by(PaymentAllocation.charge_id)
            .all()
        )
        return {charge_id: int(total) for charge_id, total in rows}

    # -- Student status rows (the /students page paid column) -----------------

    def billed_periods(self) -> list[tuple[int, int]]:
        """Every (year, month) with at least one charge, newest first.

        Only charged months are listed — the paid column and status filter mean
        nothing until a month has been billed.
        """
        with self._session() as session:
            rows = session.query(Charge.year, Charge.month).distinct().all()
        return sorted({(int(year), int(month)) for year, month in rows}, reverse=True)

    def student_status_rows(
        self,
        students: Iterable[Student],
        month: int,
        year: int,
        status: str = "",
    ) -> list[StudentStatusRow]:
        """The given students with their paid status for one month.

        A student carries a status only when they hold a charge for that month;
        never-billed students come back with ``paid_status=None``. When a
        ``status`` filter is active, never-billed students are dropped from the
        result — only students billed that month can match a status.
        """
        ids = [student.id for student in students]
        rows = [StudentStatusRow(student=student, paid_status=None, remaining_cents=0) for student in students]
        if not ids:
            return rows
        with self._session() as session:
            charges = (
                session.query(Charge)
                .options(joinedload(Charge.adjustments))
                .filter(
                    Charge.month == month,
                    Charge.year == year,
                    Charge.student_id.in_(ids),
                )
                .all()
            )
            paid_by_charge = self._paid_cents_by_charge(session, [c.id for c in charges])
        paid_map: dict[int, tuple[str, int]] = {}
        for charge in charges:
            net = net_cents(charge, list(charge.adjustments))
            paid = paid_by_charge.get(charge.id, 0)
            paid_map[charge.student_id] = self._classify_status(net, paid)
        for row in rows:
            paid_state = paid_map.get(row.student.id)
            if paid_state is not None:
                row.paid_status, row.remaining_cents = paid_state
        if status:
            rows = [row for row in rows if row.paid_status == status]
        return rows

    # -- Summarized finance --------------------------------------------------

    def finance_summary(self, month: int, year: int) -> FinanceSummary:
        """One month's income/expenses/net plus live arrears and credits."""
        report = self.income_vs_expense(month, year)
        arrears_cents = sum(
            line.owed_cents
            for line in self._arrears_lines(date(year, month, 1))
        )
        credits_cents = self._credits_total()
        rows = [
            SummaryRow("Income (payments)", report.income_cents),
            SummaryRow("Expenses", report.expenses_cents),
            SummaryRow("Net cash flow", report.net_cents),
            SummaryRow("Outstanding unpaid fees", arrears_cents),
            SummaryRow("Credit balances", credits_cents),
        ]
        return FinanceSummary(
            month=month,
            year=year,
            period_label=report.period_label,
            income_cents=report.income_cents,
            expenses_cents=report.expenses_cents,
            net_cents=report.net_cents,
            arrears_cents=arrears_cents,
            credits_cents=credits_cents,
            rows=rows,
        )

    # -- Student list --------------------------------------------------------

    def student_list(self, class_id: int | None = None) -> StudentListReport:
        """The register: every student (or one class) with class and fee."""
        with self._session() as session:
            class_name = (
                self._class_name(session, class_id) if class_id is not None else None
            )
            query = session.query(Student).options(joinedload(Student.school_class))
            if class_id is not None:
                query = query.filter(Student.class_id == class_id)
            students = query.all()
            fee_items = session.query(FeeItem).all()

        fee_by_class: dict[int, int] = {}
        for item in fee_items:
            fee_by_class[item.class_id] = fee_by_class.get(item.class_id, 0) + item.amount_cents

        lines = [
            StudentListLine(
                student=student,
                class_name=student.school_class.name,
                class_status=student.school_class.status,
                student_status=student.status,
                monthly_fee_cents=fee_by_class.get(student.class_id, 0),
            )
            for student in students
        ]
        lines.sort(key=self._student_sort_key)
        active_count = sum(1 for line in lines if line.student_status == StudentStatus.ACTIVE)
        return StudentListReport(
            class_id=class_id,
            class_name=class_name,
            active_count=active_count,
            inactive_count=len(lines) - active_count,
            lines=lines,
        )

    # -- Dashboard -----------------------------------------------------------

    def dashboard(self, today: date | None = None) -> DashboardData:
        """The dashboard: current-month KPIs, six-month series, and charts."""
        today = today or date.today()
        month, year = today.month, today.year
        income_expense = self.income_vs_expense(month, year)
        arrears_lines = self._arrears_lines(today)

        band_counts: dict[str, int] = {}
        for line in arrears_lines:
            band_counts[line.age_band] = band_counts.get(line.age_band, 0) + 1

        monthly: list[PeriodLine] = []
        cursor_year, cursor_month = year, month
        periods: list[tuple[int, int]] = []
        for _ in range(DASHBOARD_MONTHS):
            periods.append((cursor_year, cursor_month))
            cursor_month -= 1
            if cursor_month == 0:
                cursor_month = 12
                cursor_year -= 1
        window_start = date(periods[-1][0], periods[-1][1], 1)
        income_by_month = self._payment_amounts_by_month(start=window_start)
        expense_by_month = self._expense_amounts_by_month(start=window_start)
        for period_year, period_month in reversed(periods):
            income = income_by_month.get((period_year, period_month), 0)
            expenses = expense_by_month.get((period_year, period_month), 0)
            monthly.append(
                PeriodLine(
                    month=period_month,
                    year=period_year,
                    label=period_label(period_month, period_year),
                    income_cents=income,
                    expenses_cents=expenses,
                    net_cents=income - expenses,
                )
            )

        return DashboardData(
            month=month,
            year=year,
            collected_cents=income_expense.income_cents,
            expenses_cents=income_expense.expenses_cents,
            arrears_cents=sum(line.owed_cents for line in arrears_lines),
            credits_cents=self._credits_total(),
            active_student_count=self._active_student_count(),
            recent_payments=self._recent_payments(),
            recent_expenses=self._recent_expenses(),
            monthly=monthly,
            arrears_band_counts=band_counts,
            category_lines=self.expense_by_category().lines,
        )

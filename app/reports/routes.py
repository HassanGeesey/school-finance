"""Reports & dashboard routes: the reporting surface and CSV exports.

Thin adapters over :class:`app.reports.service.ReportService`. Everything here
is read-only and open to any logged-in user — the Finance officer role exists
for exactly this. Each report renders through the shared report frame template
(``reports/_frame.html``) — filter bar, summary line, table, Export CSV — and
offers a matching CSV export at the same path with a ``.csv`` suffix, driven by
the same query parameters. The dashboard (served at the root by ``main.py``)
gets its context assembled here via :func:`dashboard_context`. Business rules
live in the service — these routes only translate query parameters, errors, and
templates.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..arrears.service import AGE_BAND_LABELS
from ..auth.deps import require_login
from ..classes.service import ClassNotFound, ClassService
from ..expenses.service import EXPENSE_METHOD_LABELS
from ..fees.service import period_label
from ..models import User
from ..payments.service import PAYMENT_METHOD_LABELS
from .service import PAID_STATUS_LABELS, ReportService

router = APIRouter(include_in_schema=False)

PAID_STATUS_TONES = {
    "paid": "success",
    "partial": "warning",
    "unpaid": "error",
}


def _service(request: Request) -> ReportService:
    service = request.app.state.reports
    assert isinstance(service, ReportService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _classes(request: Request) -> ClassService:
    service = request.app.state.classes
    assert isinstance(service, ClassService)
    return service


# -- Query parsing -----------------------------------------------------------


def _period_parts(period: str) -> tuple[int, int] | None:
    """Parse a ``YYYY-MM`` value into a ``(year, month)`` pair, or ``None``.

    Callers must swap to ``(month, year)`` before use — see ``_resolve_period``.
    """
    if not period:
        return None
    try:
        year, month = (int(part) for part in period.split("-"))
    except (TypeError, ValueError):
        return None
    return year, month


def _require_month(month: int) -> int:
    """Reject a month outside 1-12 with a client error instead of a 500."""
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
    return month


def _resolve_period(
    period: str, month: int | None, year: int | None
) -> tuple[int, int]:
    """The selected (month, year): ``period`` wins, else ``month``/``year``, else today."""
    parts = _period_parts(period)
    if parts is not None:
        period_year, period_month = parts
        return _require_month(period_month), period_year
    today = date.today()
    return _require_month(month or today.month), (year or today.year)


def _period_value(month: int, year: int) -> str:
    return f"{year:04d}-{month:02d}"


def _period_options(periods: list[tuple[int, int]]) -> list[tuple[str, str]]:
    """(value, label) pairs for the month dropdown, newest first."""
    return [
        (f"{year:04d}-{month:02d}", period_label(month, year))
        for year, month in periods
    ]


def _class_options(request: Request) -> list[tuple[int, str]]:
    return [
        (summary.cls.id, summary.cls.name)
        for summary in _classes(request).list_class_summaries()
    ]


# -- CSV ---------------------------------------------------------------------


def _csv_field(value: object) -> str:
    text = str(value)
    if text.startswith(("=", "+", "@", "\t")):
        text = "'" + text
    if any(char in text for char in (",", '"', "\n", "\r")):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _csv(rows: Iterable[Iterable[object]]) -> str:
    return "\r\n".join(
        ",".join(_csv_field(cell) for cell in row) for row in rows
    ) + "\r\n"


def _csv_response(text: str, *, filename: str = "report") -> Response:
    return Response(
        content="\ufeff" + text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


def _amount(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _frame_context(
    request: Request,
    *,
    title: str,
    subtitle: str,
    page_url: str,
    export_url: str,
    export_params: dict[str, str],
    selected_period: str = "",
    selected_class_id: int | None = None,
    **extra: object,
) -> dict[str, object]:
    context: dict[str, object] = {
        "report_title": title,
        "report_subtitle": subtitle,
        "page_url": page_url,
        "export_url": export_url,
        "export_params": export_params,
        "period": selected_period,
        "period_options": _period_options(_service(request).list_periods()),
        "class_options": _class_options(request),
        "selected_class_id": selected_class_id,
    }
    context.update(extra)
    return context


def _render_report(request: Request, *, template: str, context: dict[str, object]) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request, name=template, context=context
    )


# -- Reports hub -------------------------------------------------------------


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    reports = [
        {
            "title": "Income vs Expense",
            "description": "Money in (payments) against money out (expenses) for a selected month, with the net.",
            "href": "/reports/income-expense",
            "icon": "arrow-path",
        },
        {
            "title": "Expense by category",
            "description": "Expenses grouped by category — for one month or all time — largest first.",
            "href": "/reports/expense-category",
            "icon": "chart-bar",
        },
        {
            "title": "Paid students",
            "description": "Who was billed for a month and whether they have paid, part-paid, or still owe.",
            "href": "/reports/paid-students",
            "icon": "receipt-percent",
        },
        {
            "title": "Summarized finance",
            "description": "A month's income, expenses, and net, together with unpaid-fee and credit balances.",
            "href": "/reports/summary",
            "icon": "banknotes",
        },
        {
            "title": "Student list",
            "description": "The register — every student (or one class) with class, status, and monthly fee.",
            "href": "/reports/students",
            "icon": "user-group",
        },
    ]
    return _templates(request).TemplateResponse(
        request=request,
        name="reports/index.html",
        context={"reports": reports},
    )


# -- Income vs Expense -------------------------------------------------------


@router.get("/reports/income-expense", response_class=HTMLResponse)
def income_expense_page(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    selected_month, selected_year = _resolve_period(period, month, year)
    report = _service(request).income_vs_expense(selected_month, selected_year)
    return _render_report(
        request,
        template="reports/income_expense.html",
        context=_frame_context(
            request,
            title="Income vs Expense",
            subtitle="Payments received against expenses recorded for a selected month.",

            page_url="/reports/income-expense",
            export_url="/reports/income-expense.csv",
            export_params={"month": str(selected_month), "year": str(selected_year)},
            selected_period=_period_value(selected_month, selected_year),
            report=report,
        ),
    )


@router.get("/reports/income-expense.csv")
def income_expense_csv(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> Response:
    selected_month, selected_year = _resolve_period(period, month, year)
    report = _service(request).income_vs_expense(selected_month, selected_year)
    rows: list[list[object]] = [
        ["Income vs Expense", report.period_label],
        ["Income (payments)", _amount(report.income_cents)],
        ["Expenses", _amount(report.expenses_cents)],
        ["Net cash flow", _amount(report.net_cents)],
        [],
        ["Payment method", "Count", "Amount"],
    ]
    rows += [
        [line.label, line.count, _amount(line.amount_cents)]
        for line in report.income_by_method
    ]
    rows += [[], ["Expense method", "Count", "Amount"]]
    rows += [
        [line.label, line.count, _amount(line.amount_cents)]
        for line in report.expense_by_method
    ]
    return _csv_response(_csv(rows), filename="income-expense")


# -- Expense by category -----------------------------------------------------


@router.get("/reports/expense-category", response_class=HTMLResponse)
def expense_category_page(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    selected_month, selected_year, selected_period = _category_period(
        period, month, year
    )
    report = _service(request).expense_by_category(
        month=selected_month, year=selected_year
    )
    export_params: dict[str, str] = {}
    if selected_month is not None and selected_year is not None:
        export_params = {"month": str(selected_month), "year": str(selected_year)}
    return _render_report(
        request,
        template="reports/expense_category.html",
        context=_frame_context(
            request,
            title="Expense by category",
            subtitle="Expenses grouped by category, largest total first.",

            page_url="/reports/expense-category",
            export_url="/reports/expense-category.csv",
            export_params=export_params,
            selected_period=selected_period,
            report=report,
        ),
    )


@router.get("/reports/expense-category.csv")
def expense_category_csv(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> Response:
    selected_month, selected_year, _ = _category_period(period, month, year)
    report = _service(request).expense_by_category(
        month=selected_month, year=selected_year
    )
    scope = "All time"
    if selected_month is not None and selected_year is not None:
        scope = period_label(selected_month, selected_year)
    rows: list[list[object]] = [
        ["Expense by category", scope],
        ["Category", "Count", "Total"],
    ]
    rows += [
        [line.category_name, line.count, _amount(line.total_cents)]
        for line in report.lines
    ]
    return _csv_response(_csv(rows), filename="expense-category")


def _category_period(
    period: str, month: int | None, year: int | None
) -> tuple[int | None, int | None, str]:
    """The category report's optional filter: ``None`` means all time."""
    parts = _period_parts(period)
    if parts is not None:
        period_year, period_month = parts
        return (
            _require_month(period_month),
            period_year,
            _period_value(period_month, period_year),
        )
    if month is not None and year is not None:
        return _require_month(month), year, _period_value(month, year)
    return None, None, ""


# -- Paid students -----------------------------------------------------------


@router.get("/reports/paid-students", response_class=HTMLResponse)
def paid_students_page(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    class_id: int | None = None,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    selected_month, selected_year = _resolve_period(period, month, year)
    try:
        report = _service(request).paid_students(
            selected_month, selected_year, class_id=class_id
        )
    except ClassNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_report(
        request,
        template="reports/paid_students.html",
        context=_frame_context(
            request,
            title="Paid students",
            subtitle="Who was billed for the month and whether they have paid.",

            page_url="/reports/paid-students",
            export_url="/reports/paid-students.csv",
            export_params=_paid_students_export_params(
                selected_month, selected_year, class_id
            ),
            selected_period=_period_value(selected_month, selected_year),
            selected_class_id=class_id,
            report=report,
            paid_status_labels=PAID_STATUS_LABELS,
            paid_status_tones=PAID_STATUS_TONES,
        ),
    )


@router.get("/reports/paid-students.csv")
def paid_students_csv(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    class_id: int | None = None,
    _user: User = Depends(require_login),
) -> Response:
    selected_month, selected_year = _resolve_period(period, month, year)
    try:
        report = _service(request).paid_students(
            selected_month, selected_year, class_id=class_id
        )
    except ClassNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows: list[list[object]] = [
        ["Paid students", report.period_label],
        ["Class", "Student", "Status", "Charged", "Paid", "Remaining"],
    ]
    rows += [
        [
            line.class_name,
            line.student.full_name,
            line.status,
            _amount(line.charge_cents),
            _amount(line.paid_cents),
            _amount(line.remaining_cents),
        ]
        for line in report.lines
    ]
    return _csv_response(_csv(rows), filename="paid-students")


def _paid_students_export_params(
    month: int, year: int, class_id: int | None
) -> dict[str, str]:
    params = {"month": str(month), "year": str(year)}
    if class_id is not None:
        params["class_id"] = str(class_id)
    return params


# -- Summarized finance ------------------------------------------------------


@router.get("/reports/summary", response_class=HTMLResponse)
def summary_page(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    selected_month, selected_year = _resolve_period(period, month, year)
    report = _service(request).finance_summary(selected_month, selected_year)
    return _render_report(
        request,
        template="reports/summary.html",
        context=_frame_context(
            request,
            title="Summarized finance",
            subtitle="A month's totals rolled up with the live unpaid-fee and credit balances.",

            page_url="/reports/summary",
            export_url="/reports/summary.csv",
            export_params={"month": str(selected_month), "year": str(selected_year)},
            selected_period=_period_value(selected_month, selected_year),
            report=report,
        ),
    )


@router.get("/reports/summary.csv")
def summary_csv(
    request: Request,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    _user: User = Depends(require_login),
) -> Response:
    selected_month, selected_year = _resolve_period(period, month, year)
    report = _service(request).finance_summary(selected_month, selected_year)
    rows: list[list[object]] = [["Summarized finance", report.period_label]]
    rows += [[row.label, _amount(row.amount_cents)] for row in report.rows]
    return _csv_response(_csv(rows), filename="summary")


# -- Student list ------------------------------------------------------------


@router.get("/reports/students", response_class=HTMLResponse)
def students_page(
    request: Request,
    class_id: int | None = None,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    try:
        report = _service(request).student_list(class_id=class_id)
    except ClassNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_report(
        request,
        template="reports/students.html",
        context=_frame_context(
            request,
            title="Student list",
            subtitle="The register: every student with their class, status, and monthly fee.",

            page_url="/reports/students",
            export_url="/reports/students.csv",
            export_params={"class_id": str(class_id)} if class_id is not None else {},
            selected_class_id=class_id,
            report=report,
        ),
    )


@router.get("/reports/students.csv")
def students_csv(
    request: Request,
    class_id: int | None = None,
    _user: User = Depends(require_login),
) -> Response:
    try:
        report = _service(request).student_list(class_id=class_id)
    except ClassNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows: list[list[object]] = [
        ["Student list", report.class_name or "All classes"],
        ["Class", "Student", "Status", "Class status", "Monthly fee"],
    ]
    rows += [
        [
            line.class_name,
            line.student.full_name,
            line.student_status,
            line.class_status,
            _amount(line.monthly_fee_cents),
        ]
        for line in report.lines
    ]
    return _csv_response(_csv(rows), filename="students")


# -- Dashboard context -------------------------------------------------------


def dashboard_context(request: Request) -> dict[str, object]:
    """Everything the root dashboard needs, including its Chart.js payloads."""
    data = _service(request).dashboard()
    return {
        "dashboard": data,
        "chart_labels": [line.label for line in data.monthly],
        "chart_income": [line.income_cents / 100 for line in data.monthly],
        "chart_expenses": [line.expenses_cents / 100 for line in data.monthly],
        "chart_bands": [
            {
                "key": key,
                "label": label,
                "count": data.arrears_band_counts.get(key, 0),
            }
            for key, label in AGE_BAND_LABELS.items()
        ],
        "chart_category_labels": [line.category_name for line in data.category_lines],
        "chart_category_values": [line.total_cents / 100 for line in data.category_lines],
        "payment_method_labels": PAYMENT_METHOD_LABELS,
        "expense_method_labels": EXPENSE_METHOD_LABELS,
    }

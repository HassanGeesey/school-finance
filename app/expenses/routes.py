"""Expenses routes: recording money out and managing expense categories.

Thin adapters over :class:`app.expenses.service.ExpenseService`. Recording an
expense (date + category + description + amount + cash/bank/other method) is
open to any logged-in user (the Finance officer role exists for exactly this);
managing the category list (add/rename/remove) is Admin-only. The record form
lives in a card on the expenses page and posts over htmx — a save re-renders
the card + list and raises a toast, with a plain-redirect fallback when htmx
isn't present. Category management happens in a modal whose forms also post over
htmx; after a successful category change the whole record card + list re-renders
so a just-added first category reveals the form. Business rules live in the
service — these routes only translate form data, errors, and templates.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..fees.service import MONTH_NAMES
from ..models import User
from ..money import format_cents
from .service import (
    EXPENSE_METHOD_LABELS,
    CategoryNotFound,
    DuplicateCategoryName,
    ExpenseError,
    ExpenseService,
)

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> ExpenseService:
    service = request.app.state.expenses
    assert isinstance(service, ExpenseService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _is_admin(user: User) -> bool:
    return user.role == "admin"


def _period_parts(period: str) -> tuple[int | None, int | None]:
    """Parse a ``YYYY-MM`` filter value into a (year, month) pair."""
    if not period:
        return None, None
    try:
        year, month = (int(part) for part in period.split("-"))
    except (TypeError, ValueError):
        return None, None
    return year, month


def _period_options(periods: list[tuple[int, int]]) -> list[tuple[str, str]]:
    return [
        (f"{year:04d}-{month:02d}", f"{MONTH_NAMES[month - 1]} {year}")
        for year, month in periods
    ]


def _toast_headers(message: str, tone: str) -> dict[str, str]:
    return {"HX-Trigger": json.dumps({"toast": {"message": message, "tone": tone}})}


def _category_toast_headers(message: str) -> dict[str, str]:
    """Toast + tell the record card's category dropdown to refresh."""
    return {
        "HX-Trigger": json.dumps(
            {
                "toast": {"message": message, "tone": "success"},
                "expense-categories-changed": True,
            }
        )
    }


def _dashboard_context(
    request: Request,
    user: User,
    *,
    filter_category: str = "",
    filter_period: str = "",
    error: str = "",
    record: dict[str, str] | None = None,
) -> dict[str, object]:
    service = _service(request)
    year, month = _period_parts(filter_period)
    selected_category = int(filter_category) if filter_category else None
    expenses = service.list_expenses(
        category_id=selected_category, month=month, year=year
    )
    return {
        "categories": service.list_categories(),
        "period_options": _period_options(service.list_periods()),
        "filter_category": filter_category,
        "filter_period": filter_period,
        "expenses": expenses,
        "total_cents": sum(e.amount_cents for e in expenses),
        "methods": EXPENSE_METHOD_LABELS,
        "today": date.today().isoformat(),
        "error": error,
        "record": record or {},
    }


def _dashboard_response(
    request: Request,
    user: User,
    *,
    filter_category: str = "",
    filter_period: str = "",
    error: str = "",
    record: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    return _templates(request).TemplateResponse(
        request=request,
        name="expenses/_dashboard.html",
        context=_dashboard_context(
            request,
            user,
            filter_category=filter_category,
            filter_period=filter_period,
            error=error,
            record=record,
        ),
        headers=headers,
    )


@router.get("/expenses", response_class=HTMLResponse)
def expenses_page(
    request: Request,
    category: str = "",
    period: str = "",
    user: User = Depends(require_login),
) -> HTMLResponse:
    context = _dashboard_context(
        request,
        user,
        filter_category=category,
        filter_period=period,
        error=request.query_params.get("err", ""),
    )
    context.update(
        {
            "is_admin": _is_admin(user),
            "categories_all": _service(request).list_categories(include_archived=True),
            "msg": request.query_params.get("msg", ""),
        }
    )
    return _templates(request).TemplateResponse(
        request=request,
        name="expenses/index.html",
        context=context,
    )


@router.get("/expenses/dashboard", response_class=HTMLResponse)
def expense_dashboard(
    request: Request,
    category: str = "",
    period: str = "",
    user: User = Depends(require_login),
) -> Response:
    """The record card + list, so the page can re-render after category changes."""
    return _dashboard_response(
        request,
        user,
        filter_category=category,
        filter_period=period,
    )


@router.post("/expenses", response_class=HTMLResponse)
def record_expense(
    request: Request,
    category_id: str = Form(""),
    description: str = Form(""),
    amount: str = Form(""),
    method: str = Form(""),
    occurred_on: str = Form(""),
    category: str = Form(""),
    period: str = Form(""),
    user: User = Depends(require_login),
) -> Response:
    record = {
        "category_id": category_id,
        "description": description,
        "amount": amount,
        "method": method,
        "occurred_on": occurred_on,
    }
    try:
        expense = _service(request).record_expense(
            user=user,
            category_id=int(category_id) if category_id else 0,
            description=description,
            amount=amount,
            method=method,
            occurred_on=occurred_on,
        )
    except (CategoryNotFound, ExpenseError) as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/expenses?{urlencode({'err': str(exc)})}", status_code=303
            )
        return _dashboard_response(
            request,
            user,
            filter_category=category,
            filter_period=period,
            error=str(exc),
            record=record,
        )
    message = f"Expense of {format_cents(expense.amount_cents)} recorded."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/expenses?{urlencode({'msg': message})}", status_code=303
        )
    return _dashboard_response(
        request,
        user,
        filter_category=category,
        filter_period=period,
        headers=_toast_headers(message, "success"),
    )


@router.post("/expenses/categories", response_class=HTMLResponse)
def add_category(
    request: Request,
    name: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_category(
        request,
        user,
        name=name,
        action=lambda svc: svc.create_category(user=user, name=name),
        success="Category added.",
    )


@router.post("/expenses/categories/{category_id}/rename", response_class=HTMLResponse)
def rename_category(
    request: Request,
    category_id: int,
    name: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_category(
        request,
        user,
        name=name,
        action=lambda svc: svc.rename_category(
            user=user, category_id=category_id, name=name
        ),
        success="Category renamed.",
    )


@router.post("/expenses/categories/{category_id}/remove", response_class=HTMLResponse)
def remove_category(
    request: Request,
    category_id: int,
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_category(
        request,
        user,
        action=lambda svc: svc.remove_category(
            user=user, category_id=category_id
        ),
        success="Category removed.",
    )


def _mutate_category(
    request: Request,
    user: User,
    *,
    action,
    success: str,
    name: str = "",
) -> Response:
    try:
        action(_service(request))
    except (CategoryNotFound, DuplicateCategoryName, ExpenseError) as exc:
        context = {
            "categories_all": _service(request).list_categories(include_archived=True),
            "error": str(exc),
            "category_name": name,
        }
        return _templates(request).TemplateResponse(
            request=request,
            name="expenses/_categories.html",
            context=context,
        )
    context = {
        "categories_all": _service(request).list_categories(include_archived=True),
        "error": "",
        "category_name": "",
    }
    return _templates(request).TemplateResponse(
        request=request,
        name="expenses/_categories.html",
        context=context,
        headers=_category_toast_headers(success),
    )

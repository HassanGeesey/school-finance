"""Payments & receipts routes: record money in, view receipts.

Thin adapters over :class:`app.payments.service.PaymentService`. Recording a
payment for a student (amount + cash/bank/other method + date + a month+year
tag, FW-16) is open to any logged-in user (the Finance officer role exists for
exactly this). The record screen surfaces the student's oldest unpaid owed
month as the default tag (FW-22-1) and warns, rather than blocks, when the tag
falls outside the owed range (FW-22-2); the service settles the tagged month's
shortfall and credits any excess. After a successful save the user lands on the
printable receipt; viewing the receipt is open to any logged-in user too.
Business rules live in the service — these routes only translate form data,
errors, and templates.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_login
from ..db import Database
from ..fees.service import MIN_YEAR, MAX_YEAR, MONTH_NAMES, InvalidPeriod, period_label
from ..models import Credit, User
from ..money import format_cents
from ..students.service import StudentNotFound, StudentService
from .service import (
    PAYMENT_METHOD_LABELS,
    PaymentError,
    PaymentNotFound,
    PaymentService,
)

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> PaymentService:
    service = request.app.state.payments
    assert isinstance(service, PaymentService)
    return service


def _students(request: Request) -> StudentService:
    service = request.app.state.students
    assert isinstance(service, StudentService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _student(request: Request, student_id: int):
    try:
        return _students(request).get_student(student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None


MAX_PICKER_RESULTS = 8


def _student_summary(request: Request, student) -> dict[str, object]:
    """A student with their live balance/credit, ready to render."""
    account = _service(request).account_summary(student.id).account
    return {
        "student": student,
        "balance_cents": account.balance_cents,
        "credits_cents": account.credits_cents,
    }


def _picker_rows(request: Request, q: str) -> list[dict[str, object]]:
    """The students matching ``q`` (capped) with live balances, for the
    search dropdown. An empty query lists students so the box works as a
    picker even before the user types.
    """
    students = _students(request).search_students(q)[:MAX_PICKER_RESULTS]
    return [_student_summary(request, student) for student in students]


def _coerce_month(raw: str) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise InvalidPeriod("Choose a valid month.") from None


def _coerce_year(raw: str) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise InvalidPeriod("Choose a valid year.") from None


def _default_tag(request: Request, student_id: int) -> tuple[int, int]:
    """The record screen's default month tag: the oldest unpaid owed month, or
    the current month when nothing is unpaid (FW-22-1)."""
    summary = _service(request).account_summary(student_id)
    if summary.oldest_unpaid is not None:
        year, month = summary.oldest_unpaid
        return month, year
    today = date.today()
    return today.month, today.year


def _period_context(request: Request, student_id: int, month: str, year: str) -> tuple[int, int]:
    """Coerce posted month/year, falling back to the record screen's default."""
    coerced_month = _coerce_month(month)
    coerced_year = _coerce_year(year)
    if coerced_month is None or coerced_year is None:
        default_month, default_year = _default_tag(request, student_id)
        coerced_month = coerced_month or default_month
        coerced_year = coerced_year or default_year
    return coerced_month, coerced_year


def _month_year_options(month: int | None, year: int | None) -> dict[str, object]:
    today = date.today()
    return {
        "month": str(month) if month is not None else "",
        "year": str(year) if year is not None else "",
        "months": [(i, MONTH_NAMES[i - 1]) for i in range(1, 13)],
        "years": list(range(today.year - 1, today.year + 3)),
    }


def _record_context(
    request: Request,
    student_id: int,
    *,
    amount: str = "",
    method: str = "",
    month: str = "",
    year: str = "",
    paid_on: str = "",
    error: str = "",
) -> dict[str, object]:
    student = _student(request, student_id)
    summary = _service(request).account_summary(student_id)
    selected_month, selected_year = _period_context(request, student_id, month, year)
    return {
        "student": student,
        "account": summary.account,
        "methods": PAYMENT_METHOD_LABELS,
        "amount": amount,
        "method": method,
        "paid_on": paid_on or date.today().isoformat(),
        "error": error,
        **_month_year_options(selected_month, selected_year),
    }


@router.get("/payments", response_class=HTMLResponse)
def payments_page(
    request: Request,
    q: str = "",
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Payments page: prototype-style record screen.

    A search box drops down the matching students; picking one swaps in its
    live balance and credit alongside the amount/method/month form and a
    receipt preview. Nothing is selected until the user chooses.
    """
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/index.html",
        context={
            "rows": _picker_rows(request, q),
            "q": q,
            "methods": PAYMENT_METHOD_LABELS,
            "today": date.today().isoformat(),
            **_month_year_options(None, None),
        },
    )


@router.get("/payments/record", response_class=HTMLResponse)
def record_payment_form(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/record.html",
        context=_record_context(request, student_id),
    )


@router.get("/payments/preview", response_class=HTMLResponse)
def payment_preview(
    request: Request,
    student_id: int = Query(...),
    amount: str = Query(""),
    month: str = Query(""),
    year: str = Query(""),
    part: str = Query("list"),
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Live confirmation line for the record screen (htmx fragment).

    Shows what a payment of ``amount`` tagged to ``month``/``year`` would
    settle and how much would become credit — nothing is written. With
    ``part=clears`` it renders just the one-line strip total instead of the
    full breakdown.
    """
    service = _service(request)
    try:
        selected_month, selected_year = _period_context(request, student_id, month, year)
        preview = (
            service.preview_application(student_id, selected_month, selected_year, amount)
            if amount
            else None
        )
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None
    except PaymentError as exc:
        preview = None
        error = str(exc)
    else:
        error = ""
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_clears.html" if part == "clears" else "payments/_preview.html",
        context={
            "preview": preview,
            "amount": amount,
            "error": error,
        },
    )


@router.get("/payments/student-picker", response_class=HTMLResponse)
def payment_student_picker(
    request: Request,
    q: str = "",
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Live student search dropdown for the record screen (htmx fragment).

    Returns the list of students matching ``q`` (with live balances) that
    drops down under the search box; clicking one calls the select fragment.
    """
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_student_options.html",
        context={"rows": _picker_rows(request, q), "q": q},
    )


@router.get("/payments/period-selects", response_class=HTMLResponse)
def payment_period_selects(
    request: Request,
    student_id: int = Query(0),
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """The record screen's month/year pickers, defaulted to the picked
    student's oldest unpaid owed month (FW-22-1).

    Swapped in over htmx when a student is selected on the split-screen record
    page, so the clerk sees the month the payment will be tagged to. With no
    student (or one who owes nothing) the pickers are blank.
    """
    month, year = None, None
    if student_id:
        try:
            month, year = _default_tag(request, student_id)
        except StudentNotFound:
            raise HTTPException(status_code=404, detail="Student not found.") from None
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_period_selects.html",
        context=_month_year_options(month, year),
    )


@router.get("/payments/student-picker/select", response_class=HTMLResponse)
def payment_student_select(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Swap a chosen student's summary card (and hidden ``student_id``) into
    the record form after a dropdown selection (htmx fragment).
    """
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_student_picker.html",
        context={"selected": _student_summary(request, _student(request, student_id)), "q": ""},
    )


@router.get("/payments/receipt-preview", response_class=HTMLResponse)
def payment_receipt_preview(
    request: Request,
    student_id: int = Query(0),
    amount: str = Query(""),
    method: str = Query("cash"),
    month: str = Query(""),
    year: str = Query(""),
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Live receipt preview for the record screen (htmx fragment).

    Shows how the printable receipt would look for the entered amount, method,
    and picked student. Nothing is written.
    """
    student = None
    if student_id:
        try:
            student = _students(request).get_student(student_id)
        except StudentNotFound:
            student = None
    if method not in PAYMENT_METHOD_LABELS:
        method = "cash"
    try:
        amount_cents = round(float(amount or "0") * 100)
    except ValueError:
        amount_cents = 0
    try:
        selected_month, selected_year = _period_context(request, student_id, month, year)
        period = period_label(selected_month, selected_year)
    except InvalidPeriod:
        period = ""
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_receipt_preview.html",
        context={
            "student": student,
            "amount_cents": amount_cents,
            "method_label": PAYMENT_METHOD_LABELS[method],
            "paid_on": date.today().isoformat(),
            "period": period,
        },
    )


@router.post("/payments/record", response_class=HTMLResponse)
def record_payment(
    request: Request,
    student_id: int = Form(...),
    amount: str = Form(""),
    method: str = Form(""),
    paid_on: str = Form(""),
    month: str = Form(""),
    year: str = Form(""),
    user: User = Depends(require_login),
) -> Response:
    try:
        selected_month, selected_year = _period_context(request, student_id, month, year)
        payment = _service(request).record_payment(
            user=user,
            student_id=student_id,
            amount=amount,
            method=method,
            paid_on=paid_on,
            month=selected_month,
            year=selected_year,
        )
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None
    except PaymentError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="payments/record.html",
            context=_record_context(
                request,
                student_id,
                amount=amount,
                method=method,
                month=str(selected_month),
                year=str(selected_year),
                paid_on=paid_on,
                error=str(exc),
            ),
            status_code=400,
        )
    return RedirectResponse(
        f"/payments/{payment.id}/receipt?{urlencode({'msg': f'Payment of {format_cents(payment.amount_cents)} recorded.'})}",
        status_code=303,
    )


@router.get("/payments/{payment_id}/receipt", response_class=HTMLResponse)
def payment_receipt(
    request: Request,
    payment_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    try:
        payment = _service(request).get_payment(payment_id)
    except PaymentNotFound:
        raise HTTPException(status_code=404, detail="Payment not found.")
    applied_cents = _applied_cents(request, payment)
    credit_cents = payment.amount_cents - applied_cents
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/receipt.html",
        context={
            "payment": payment,
            "applied_rows": [
                {
                    "period_label": period_label(payment.month, payment.year),
                    "amount_cents": applied_cents,
                }
            ],
            "applied_cents": applied_cents,
            "credit_cents": credit_cents,
            "msg": request.query_params.get("msg", ""),
        },
    )


def _applied_cents(request: Request, payment) -> int:
    """The part of a payment that settled its tagged month (excess became credit)."""
    db: Database = request.app.state.db
    with db.session() as session:
        credit_cents = sum(
            row.amount_cents
            for row in session.query(Credit.amount_cents)
            .filter(Credit.payment_id == payment.id)
            .all()
        )
    return max(payment.amount_cents - credit_cents, 0)

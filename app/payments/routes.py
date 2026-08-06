"""Payments & receipts routes: record money in, view receipts.

Thin adapters over :class:`app.payments.service.PaymentService`. Recording a
payment for a student (amount + cash/bank/other method + date) is open to any
logged-in user (the Finance officer role exists for exactly this), and the
service applies it oldest-unpaid-first, credits any excess, and audits the
whole payment. After a successful save the user lands on the printable
receipt; viewing the receipt is open to any logged-in user too. Business
rules live in the service — these routes only translate form data, errors, and
templates.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_login
from ..fees.service import period_label
from ..models import User
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


def _record_context(
    request: Request,
    student_id: int,
    *,
    amount: str = "",
    method: str = "",
    paid_on: str = "",
    error: str = "",
) -> dict[str, object]:
    student = _student(request, student_id)
    account = _service(request).student_account(student_id)
    return {
        "student": student,
        "account": account,
        "methods": PAYMENT_METHOD_LABELS,
        "amount": amount,
        "method": method,
        "paid_on": paid_on or date.today().isoformat(),
        "error": error,
    }


@router.get("/payments", response_class=HTMLResponse)
def payments_page(
    request: Request,
    q: str = "",
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Payments page: search a student to record money in, plus recent payments."""
    rows = _students(request).search_students(q)
    recent = _service(request).list_recent_payments()
    student_rows = [
        {"student": student, "balance_cents": _service(request).student_balance(student.id)}
        for student in rows
    ]
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/index.html",
        context={"rows": student_rows, "q": q, "recent": recent},
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
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Live confirmation line for the record screen (htmx fragment).

    Shows which charges a payment of ``amount`` would clear (oldest unpaid
    first) and how much would become a credit — nothing is written.
    """
    service = _service(request)
    try:
        preview = service.preview_application(student_id, amount) if amount else None
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None
    except PaymentError as exc:
        preview = None
        error = str(exc)
    else:
        error = ""
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/_preview.html",
        context={
            "preview": preview,
            "amount": amount,
            "error": error,
        },
    )


@router.post("/payments/record", response_class=HTMLResponse)
def record_payment(
    request: Request,
    student_id: int = Form(...),
    amount: str = Form(""),
    method: str = Form(""),
    paid_on: str = Form(""),
    user: User = Depends(require_login),
) -> Response:
    try:
        payment = _service(request).record_payment(
            user=user,
            student_id=student_id,
            amount=amount,
            method=method,
            paid_on=paid_on,
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
    applied_cents = sum(a.amount_cents for a in payment.allocations)
    return _templates(request).TemplateResponse(
        request=request,
        name="payments/receipt.html",
        context={
            "payment": payment,
            "allocation_rows": [
                {
                    "period_label": period_label(a.charge.month, a.charge.year),
                    "amount_cents": a.amount_cents,
                }
                for a in payment.allocations
            ],
            "applied_cents": applied_cents,
            "credit_cents": max(payment.amount_cents - applied_cents, 0),
            "msg": request.query_params.get("msg", ""),
        },
    )

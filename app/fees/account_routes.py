"""Student account + adjustments routes.

Thin adapters over :class:`app.fees.service.AdjustmentsService`. Viewing a
student's account — charges with item breakdown, adjustments, and the live
balance — is open to any logged-in user. Making an adjustment (an extra fee
item or a waiver/discount) is Admin-only and audited by the service layer.

The adjust modal posts over HTMX and swaps the whole account-finance section in
place (``HX-Retarget: #account-finance``) with a toast on save; on error it
re-renders the modal in place with the reason, leaving it open.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..models import AdjustmentKinds, User
from ..money import format_cents
from ..payments.service import PaymentService
from ..students.service import StudentNotFound
from .service import AdjustmentError, AdjustmentsService, ChargeNotFound

router = APIRouter(include_in_schema=False)

ADJUSTMENT_KIND_LABELS = {
    AdjustmentKinds.EXTRA: "Extra",
    AdjustmentKinds.WAIVER: "Waiver",
}


def _adjustments(request: Request) -> AdjustmentsService:
    service = request.app.state.adjustments
    assert isinstance(service, AdjustmentsService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _student(request: Request, student_id: int):
    try:
        return request.app.state.students.get_student(student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None


def _payments(request: Request) -> PaymentService:
    service = request.app.state.payments
    assert isinstance(service, PaymentService)
    return service


def _finance_context(request: Request, student) -> dict[str, object]:
    account = _payments(request).student_account(student.id)
    return {
        "student": student,
        "account": account,
        "lines": account.charges,
        "balance": account.balance_cents,
    }


def _modal_response(
    request: Request,
    line,
    *,
    error: str,
    kind: str = "",
    label: str = "",
    amount: str = "",
) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_adjust_modal.html",
        context={
            "line": line,
            "kinds": ADJUSTMENT_KIND_LABELS,
            "kind": kind,
            "label": label,
            "amount": amount,
            "error": error,
        },
    )


def _success_message(kind: str, adjustment) -> str:
    amount = format_cents(adjustment.amount_cents)
    if kind == AdjustmentKinds.EXTRA:
        return f"Added extra “{adjustment.label}” ({amount})."
    return f"Applied waiver “{adjustment.label}” ({amount})."


@router.get("/students/{student_id}/account", response_class=HTMLResponse)
def student_account(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    student = _student(request, student_id)
    context = _finance_context(request, student)
    context["msg"] = request.query_params.get("msg", "")
    context["err"] = request.query_params.get("err", "")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/account.html",
        context=context,
    )


@router.get("/charges/{charge_id}/adjust-form", response_class=HTMLResponse)
def adjust_form(
    request: Request,
    charge_id: int,
    _user: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        line = _adjustments(request).get_charge_line(charge_id)
    except ChargeNotFound:
        raise HTTPException(status_code=404, detail="Charge not found.")
    return _modal_response(request, line, error="")


@router.post("/charges/{charge_id}/adjust", response_class=HTMLResponse)
def adjust_charge(
    request: Request,
    charge_id: int,
    kind: str = Form(""),
    label: str = Form(""),
    amount: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    adjustments = _adjustments(request)
    try:
        charge = adjustments.get_charge(charge_id)
    except ChargeNotFound:
        raise HTTPException(status_code=404, detail="Charge not found.")

    if kind not in ADJUSTMENT_KIND_LABELS:
        return _modal_response(
            request,
            adjustments.get_charge_line(charge_id),
            error="Choose Extra or Waiver.",
            kind=kind,
            label=label,
            amount=amount,
        )

    try:
        if kind == AdjustmentKinds.EXTRA:
            adjustment = adjustments.add_extra(
                user=user, charge_id=charge_id, label=label, amount=amount
            )
        else:
            adjustment = adjustments.apply_waiver(
                user=user, charge_id=charge_id, label=label, amount=amount
            )
    except AdjustmentError as exc:
        return _modal_response(
            request,
            adjustments.get_charge_line(charge_id),
            error=str(exc),
            kind=kind,
            label=label,
            amount=amount,
        )

    message = _success_message(kind, adjustment)
    if not _is_htmx(request):
        return RedirectResponse(
            f"/students/{charge.student_id}/account?{urlencode({'msg': message})}",
            status_code=303,
        )
    context = _finance_context(request, _student(request, charge.student_id))
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_account_finance.html",
        context=context,
        headers={
            "HX-Retarget": "#account-finance",
            "HX-Trigger": json.dumps({"toast": {"message": message, "tone": "success"}}),
        },
    )

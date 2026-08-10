"""Fee template routes: the Admin's templates page and its HTMX partials.

Thin adapters over :class:`app.fees.service.TemplateService`. Viewing the list
is open to any logged-in user; creating, editing, and archiving templates is
Admin-only (Q24) and audited by the service layer. The add/edit form lives in a
modal opened by the page action and posts over htmx — a save returns a fresh
form and raises a toast + ``templates-changed`` event (which closes the modal
and refreshes the list), with a plain-redirect fallback when htmx isn't present.
Editing a template's amount asks for the month the change takes effect (default:
next month); the amount itself is the current amount until that month.
"""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..models import User
from ..money import format_cents, format_input_cents
from .service import (
    MONTH_NAMES,
    InvalidPeriod,
    TemplateError,
    TemplateNotFound,
    TemplateService,
    default_effective_month,
)

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> TemplateService:
    service = request.app.state.fees
    assert isinstance(service, TemplateService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _is_admin(request: Request) -> bool:
    user = getattr(request.state, "user", None)
    return user is not None and user.role == "admin"


def _coerce_month(raw: str) -> int | None:
    """Empty means "use the default (next month)"; junk is rejected."""
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


def _list_context(request: Request) -> dict[str, object]:
    service = _service(request)
    return {
        "templates": service.list_templates(),
        "counts": service.linked_student_counts(),
        "is_admin": _is_admin(request),
    }


def _list_response(
    request: Request,
    *,
    toast: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    merged = dict(headers or {})
    if toast is not None:
        merged["HX-Trigger"] = json.dumps({"toast": toast})
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_templates_list.html",
        context=_list_context(request),
        headers=merged or None,
    )


def _form_response(
    request: Request,
    *,
    template=None,
    error: str = "",
    name: str = "",
    amount: str = "",
    month: str = "",
    year: str = "",
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    now = datetime.now()
    default_month, default_year = default_effective_month()
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_template_form.html",
        context={
            "template": template,
            "action": (
                f"/fees/templates/{template.id}/edit"
                if template is not None
                else "/fees/templates"
            ),
            "name": name,
            "amount": amount,
            "month": month,
            "year": year,
            "default_month": str(default_month),
            "default_year": str(default_year),
            "months": [(i, MONTH_NAMES[i - 1]) for i in range(1, 13)],
            "years": list(range(now.year, now.year + 2)),
            "error": error,
        },
        headers=headers,
    )


def _success_headers(message: str) -> dict[str, str]:
    """Toast + tell the page the templates changed (closes the modal, refreshes)."""
    return {
        "HX-Trigger": json.dumps(
            {
                "toast": {"message": message, "tone": "success"},
                "templates-changed": True,
            }
        )
    }


def _redirect(msg_or_err: str, *, err: bool = False) -> RedirectResponse:
    params = {"err": msg_or_err} if err else {"msg": msg_or_err}
    return RedirectResponse(f"/fees?{urlencode(params)}", status_code=303)


@router.get("/fees", response_class=HTMLResponse)
def fees_page(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/index.html",
        context={
            **_list_context(request),
            "msg": request.query_params.get("msg", ""),
            "err": request.query_params.get("err", ""),
        },
    )


@router.get("/fees/templates/list", response_class=HTMLResponse)
def templates_list(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
    """The list alone, so the page can refresh it after a template change."""
    return _list_response(request)


@router.get("/fees/templates/new-form", response_class=HTMLResponse)
def new_template_form(request: Request, _user: User = Depends(require_admin)) -> HTMLResponse:
    """The blank create form, loaded into the modal by the "New template" action."""
    return _form_response(request)


@router.get("/fees/templates/{template_id}/edit-form", response_class=HTMLResponse)
def edit_template_form(
    request: Request, template_id: int, _user: User = Depends(require_admin)
) -> HTMLResponse:
    """The prefilled edit form, loaded into the modal by a row's Edit action."""
    try:
        template = _service(request).get_template(template_id)
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="Fee template not found.")
    return _form_response(
        request,
        template=template,
        name=template.name,
        amount=format_input_cents(template.amount_cents),
    )


@router.post("/fees/templates", response_class=HTMLResponse)
def create_template(
    request: Request,
    name: str = Form(""),
    amount: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).create_template(user=user, name=name, amount=amount)
    except TemplateError as exc:
        if not _is_htmx(request):
            return _redirect(str(exc), err=True)
        return _form_response(request, error=str(exc), name=name, amount=amount)
    message = "Fee template created."
    if not _is_htmx(request):
        return _redirect(message)
    return _form_response(request, headers=_success_headers(message))


@router.post("/fees/templates/{template_id}/edit", response_class=HTMLResponse)
def edit_template(
    request: Request,
    template_id: int,
    name: str = Form(""),
    amount: str = Form(""),
    month: str = Form(""),
    year: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        template = _service(request).update_template(
            user=user,
            template_id=template_id,
            name=name,
            amount=amount,
            month=_coerce_month(month),
            year=_coerce_year(year),
        )
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="Fee template not found.")
    except TemplateError as exc:
        if not _is_htmx(request):
            return _redirect(str(exc), err=True)
        current = _service(request).get_template(template_id)
        return _form_response(
            request,
            template=current,
            error=str(exc),
            name=name,
            amount=amount,
            month=month,
            year=year,
        )
    message = "Fee template updated."
    if not _is_htmx(request):
        return _redirect(message)
    return _form_response(request, headers=_success_headers(message))


@router.post("/fees/templates/{template_id}/archive", response_class=HTMLResponse)
def archive_template(
    request: Request,
    template_id: int,
    user: User = Depends(require_admin),
) -> Response:
    return _status_mutation(request, template_id, user, archive=True)


@router.post("/fees/templates/{template_id}/restore", response_class=HTMLResponse)
def restore_template(
    request: Request,
    template_id: int,
    user: User = Depends(require_admin),
) -> Response:
    return _status_mutation(request, template_id, user, archive=False)


def _status_mutation(
    request: Request, template_id: int, user: User, *, archive: bool
) -> Response:
    service = _service(request)
    try:
        if archive:
            service.archive_template(user=user, template_id=template_id)
            message = "Fee template archived."
        else:
            service.restore_template(user=user, template_id=template_id)
            message = "Fee template restored."
    except TemplateNotFound:
        raise HTTPException(status_code=404, detail="Fee template not found.")
    if not _is_htmx(request):
        return _redirect(message)
    return _list_response(request, toast={"message": message, "tone": "success"})

"""Fee generation routes: the monthly billing page and its HTMX partials.

Thin adapters over :class:`app.fees.service.FeeService`. The page is a single
card (Class/All + Month + Year) whose "Review and generate" button opens a
confirm dialog with the per-class breakdown. Confirming posts to
``/fees/generate`` which swaps the card in place and raises a toast. Any
logged-in user may generate fees (the Finance officer role exists for exactly
this); every generation is audited by the service layer.
"""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_login
from ..classes.service import ClassNotFound
from ..models import ClassStatus, User
from ..money import format_cents
from .service import (
    FeeError,
    FeeService,
    GenerationPreview,
    GenerationResult,
    InvalidPeriod,
    MONTH_NAMES,
)

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> FeeService:
    service = request.app.state.fees
    assert isinstance(service, FeeService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _coerce_class_id(raw: str) -> int | None:
    """Empty string means "All classes"."""
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ClassNotFound("Choose a class.") from None


def _coerce_period(month_raw: str, year_raw: str) -> tuple[int, int]:
    try:
        return int(month_raw), int(year_raw)
    except (TypeError, ValueError):
        raise InvalidPeriod("Choose a month and a year.") from None


def _safe_int(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _period_label(month: int, year: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}"


def _class_options(request: Request) -> list[tuple[str, str]]:
    """Active classes for the dropdown, labelled with their monthly fee."""
    options: list[tuple[str, str]] = []
    for summary in request.app.state.classes.list_class_summaries():
        if summary.cls.status == ClassStatus.ACTIVE:
            options.append(
                (
                    str(summary.cls.id),
                    f"{summary.cls.name} — {format_cents(summary.monthly_total_cents)}/month",
                )
            )
    return options


def _card_context(
    request: Request,
    *,
    msg: str = "",
    err: str = "",
    selected_class_id: str = "",
    month: int | None = None,
    year: int | None = None,
) -> dict[str, object]:
    now = datetime.now()
    return {
        "class_options": _class_options(request),
        "months": [(i, MONTH_NAMES[i - 1]) for i in range(1, 13)],
        "years": list(range(now.year - 5, now.year + 2)),
        "default_month": now.month,
        "default_year": now.year,
        "month": month,
        "year": year,
        "selected_class_id": selected_class_id,
        "msg": msg,
        "err": err,
    }


def _card_response(
    request: Request,
    *,
    msg: str = "",
    err: str = "",
    toast: dict[str, str] | None = None,
    selected_class_id: str = "",
    month: int | None = None,
    year: int | None = None,
) -> Response:
    context = _card_context(
        request,
        msg=msg,
        err=err,
        selected_class_id=selected_class_id,
        month=month,
        year=year,
    )
    headers = {"HX-Trigger": json.dumps({"toast": toast})} if toast else None
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_generate_card.html",
        context=context,
        headers=headers,
    )


def _preview_response(
    request: Request,
    *,
    preview: GenerationPreview | None = None,
    period: str = "",
    error: str = "",
) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_preview.html",
        context={"preview": preview, "period": period, "error": error},
    )


def _success_message(result: GenerationResult) -> tuple[str, str]:
    """Human summary for the success alert/toast."""
    month, year = result.month, result.year
    period = _period_label(month, year)
    if not result.generated:
        return (
            f"Nothing new was generated for {period} — every class in scope was "
            "already billed or is not eligible.",
            "info",
        )
    total = format_cents(result.total_cents)
    count = result.charges_created
    if len(result.generated) == 1:
        name = result.generated[0].class_name
        message = f"{name} — {period}: {count} charge(s), {total}."
    else:
        message = f"Generated {period} fees: {count} charge(s), {total}."
    if result.skipped:
        message += f" {len(result.skipped)} class(es) skipped."
    return message, "success"


@router.get("/fees", response_class=HTMLResponse)
def fees_page(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/index.html",
        context=_card_context(
            request,
            msg=request.query_params.get("msg", ""),
            err=request.query_params.get("err", ""),
        ),
    )


@router.post("/fees/preview", response_class=HTMLResponse)
def preview_fees(
    request: Request,
    class_id: str = Form(""),
    month: str = Form(""),
    year: str = Form(""),
    _user: User = Depends(require_login),
) -> HTMLResponse:
    service = _service(request)
    try:
        selected = _coerce_class_id(class_id)
        selected_month, selected_year = _coerce_period(month, year)
        preview = service.preview(selected, selected_month, selected_year)
    except (FeeError, ClassNotFound) as exc:
        return _preview_response(request, error=str(exc))
    if (
        selected is not None
        and preview.lines
        and preview.lines[0].skip_reason is not None
    ):
        skip_error = service._error_for_reason(
            preview.lines[0].skip_reason,
            preview.lines[0].class_name,
            _period_label(selected_month, selected_year),
        )
        return _preview_response(request, error=str(skip_error))
    return _preview_response(
        request,
        preview=preview,
        period=_period_label(selected_month, selected_year),
    )


@router.post("/fees/generate", response_class=HTMLResponse)
def generate_fees(
    request: Request,
    class_id: str = Form(""),
    month: str = Form(""),
    year: str = Form(""),
    user: User = Depends(require_login),
) -> Response:
    try:
        selected = _coerce_class_id(class_id)
        selected_month, selected_year = _coerce_period(month, year)
        result = _service(request).generate(
            user=user, class_id=selected, month=selected_month, year=selected_year
        )
    except (FeeError, ClassNotFound) as exc:
        msg, err, toast = "", str(exc), {"message": str(exc), "tone": "error"}
    else:
        msg, tone = _success_message(result)
        err, toast = "", {"message": msg, "tone": tone}

    if not _is_htmx(request):
        params = {"msg": msg} if msg else {"err": err}
        return RedirectResponse(f"/fees?{urlencode(params)}", status_code=303)
    return _card_response(
        request,
        msg=msg,
        err=err,
        toast=toast,
        selected_class_id=class_id,
        month=_safe_int(month),
        year=_safe_int(year),
    )

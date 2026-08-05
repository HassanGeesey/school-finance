"""Class routes: listing and editing classes and their fee structures.

Thin adapters over :class:`app.classes.service.ClassService`. Viewing is open to
any logged-in user (Finance needs to see classes to generate fees); every
mutation is Admin-only and audited by the service layer.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..models import User
from .service import CLASS_STATUS_LABELS, ClassError, ClassNotFound, ClassService, FeeItemNotFound

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> ClassService:
    service = request.app.state.classes
    assert isinstance(service, ClassService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _status_options() -> list[tuple[str, str]]:
    return list(CLASS_STATUS_LABELS.items())


def _redirect_detail(class_id: int, msg: str) -> RedirectResponse:
    return RedirectResponse(f"/classes/{class_id}?{urlencode({'msg': msg})}", status_code=303)


def _detail_response(
    request: Request,
    class_id: int,
    *,
    error: str = "",
    msg: str = "",
    fee_name: str = "",
    fee_amount: str = "",
    class_name: str | None = None,
    class_status: str | None = None,
) -> HTMLResponse:
    service = _service(request)
    try:
        summary = service.class_summary(class_id)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/detail.html",
        context={
            "cls": summary.cls,
            "items": summary.items,
            "monthly_total_cents": summary.monthly_total_cents,
            "status_options": _status_options(),
            "error": error,
            "msg": msg,
            "fee_name": fee_name,
            "fee_amount": fee_amount,
            "class_name": class_name if class_name is not None else summary.cls.name,
            "class_status": class_status if class_status is not None else summary.cls.status,
        },
        status_code=400 if error else 200,
    )


@router.get("/classes", response_class=HTMLResponse)
def class_index(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/index.html",
        context={
            "rows": _service(request).list_class_summaries(),
            "msg": request.query_params.get("msg", ""),
        },
    )


@router.get("/classes/new", response_class=HTMLResponse)
def new_class_form(
    request: Request, _user: User = Depends(require_admin)
) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/form.html",
        context={"name": "", "status": "", "status_options": _status_options(), "error": ""},
    )


@router.post("/classes", response_class=HTMLResponse)
def create_class(
    request: Request,
    name: str = Form(""),
    status: str = Form("active"),
    user: User = Depends(require_admin),
) -> Response:
    try:
        cls = _service(request).create_class(user=user, name=name, status=status)
    except ClassError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="classes/form.html",
            context={
                "name": name,
                "status": status,
                "status_options": _status_options(),
                "error": str(exc),
            },
            status_code=400,
        )
    return _redirect_detail(cls.id, "Class created.")


@router.get("/classes/{class_id}", response_class=HTMLResponse)
def class_detail(
    request: Request, class_id: int, _user: User = Depends(require_login)
) -> HTMLResponse:
    return _detail_response(
        request,
        class_id,
        msg=request.query_params.get("msg", ""),
    )


@router.post("/classes/{class_id}/edit", response_class=HTMLResponse)
def edit_class(
    request: Request,
    class_id: int,
    name: str = Form(""),
    status: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        cls = _service(request).update_class(
            user=user, class_id=class_id, name=name, status=status
        )
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    except ClassError as exc:
        return _detail_response(
            request,
            class_id,
            error=str(exc),
            class_name=name,
            class_status=status,
        )
    return _redirect_detail(cls.id, "Class updated.")


@router.post("/classes/{class_id}/fee-items", response_class=HTMLResponse)
def add_fee_item(
    request: Request,
    class_id: int,
    name: str = Form(""),
    amount: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).add_fee_item(user=user, class_id=class_id, name=name, amount=amount)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    except ClassError as exc:
        return _detail_response(
            request,
            class_id,
            error=str(exc),
            fee_name=name,
            fee_amount=amount,
        )
    return _redirect_detail(class_id, "Fee item added.")


@router.post("/classes/{class_id}/fee-items/{item_id}/edit", response_class=HTMLResponse)
def edit_fee_item(
    request: Request,
    class_id: int,
    item_id: int,
    name: str = Form(""),
    amount: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).update_fee_item(
            user=user, class_id=class_id, item_id=item_id, name=name, amount=amount
        )
    except FeeItemNotFound:
        raise HTTPException(status_code=404, detail="Fee item not found.")
    except ClassError as exc:
        return _detail_response(
            request,
            class_id,
            error=str(exc),
            fee_name=name,
            fee_amount=amount,
        )
    return _redirect_detail(class_id, "Fee item updated.")


@router.post("/classes/{class_id}/fee-items/{item_id}/delete", response_class=HTMLResponse)
def remove_fee_item(
    request: Request,
    class_id: int,
    item_id: int,
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).remove_fee_item(user=user, class_id=class_id, item_id=item_id)
    except FeeItemNotFound:
        raise HTTPException(status_code=404, detail="Fee item not found.")
    return _redirect_detail(class_id, "Fee item removed.")

"""Class routes: listing and editing classes and their default fee template.

Thin adapters over :class:`app.classes.service.ClassService`. Viewing is open to
any logged-in user (Finance needs to see classes to follow students); every
mutation is Admin-only and audited by the service layer. The default fee
template picker draws its options from the Admin-managed fee templates
(:class:`app.fees.service.TemplateService`).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..fees.service import TemplateService
from ..models import User
from .service import CLASS_STATUS_LABELS, ClassError, ClassNotFound, ClassService

router = APIRouter(include_in_schema=False)


@dataclass
class TemplateOption:
    """One choice in the class default-template picker (archived ones are flagged)."""

    id: int
    name: str
    amount_cents: int
    archived: bool


def _service(request: Request) -> ClassService:
    service = request.app.state.classes
    assert isinstance(service, ClassService)
    return service


def _template_service(request: Request) -> TemplateService:
    service = request.app.state.fees
    assert isinstance(service, TemplateService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _status_options() -> list[tuple[str, str]]:
    return list(CLASS_STATUS_LABELS.items())


def _coerce_template_id(raw: str) -> int | None:
    """Turn a posted picker value into a template id, or ``None`` for "no default"."""
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ClassError("Choose a valid fee template.") from None


def _template_options(
    request: Request, current_id: int | None = None
) -> list[TemplateOption]:
    """Active templates for the picker, plus the current default if it is archived."""
    service = _template_service(request)

    def option(template) -> TemplateOption:
        return TemplateOption(
            id=template.id,
            name=template.name,
            amount_cents=template.amount_cents,
            archived=template.archived,
        )

    options = [option(template) for template in service.list_active_templates()]
    if current_id is not None and all(option.id != current_id for option in options):
        options.append(option(service.get_template(current_id)))
    return options


def _valid_template_ids(request: Request, current_id: int | None) -> set[int]:
    """Template ids the picker offers: live templates plus the current default
    (which may be archived and still show in the picker)."""
    ids = {template.id for template in _template_service(request).list_active_templates()}
    if current_id is not None:
        ids.add(current_id)
    return ids


def _redirect_detail(class_id: int, msg: str) -> RedirectResponse:
    return RedirectResponse(f"/classes/{class_id}?{urlencode({'msg': msg})}", status_code=303)


def _detail_context(
    request: Request,
    summary,
    students,
    *,
    error: str = "",
    msg: str = "",
    class_name: str | None = None,
    class_status: str | None = None,
    default_template_id: str | None = None,
) -> dict[str, object]:
    """Context for the class detail page, including the default-template picker."""
    current_id = summary.cls.default_template_id
    picked = (
        default_template_id
        if default_template_id is not None
        else (str(current_id) if current_id is not None else "")
    )
    return {
        "cls": summary.cls,
        "monthly_total_cents": summary.monthly_total_cents,
        "default_template": summary.cls.default_template,
        "default_template_id": picked,
        "template_options": _template_options(request, current_id),
        "status_options": _status_options(),
        "error": error,
        "msg": msg,
        "class_name": class_name if class_name is not None else summary.cls.name,
        "class_status": class_status if class_status is not None else summary.cls.status,
        "students": students,
    }


def _detail_response(
    request: Request,
    class_id: int,
    *,
    error: str = "",
    msg: str = "",
    class_name: str | None = None,
    class_status: str | None = None,
    default_template_id: str | None = None,
) -> HTMLResponse:
    service = _service(request)
    try:
        summary = service.class_summary(class_id)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    students = request.app.state.students.list_students(class_id)
    context = _detail_context(
        request,
        summary,
        students,
        error=error,
        msg=msg,
        class_name=class_name,
        class_status=class_status,
        default_template_id=default_template_id,
    )
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/detail.html",
        context=context,
        status_code=400 if error else 200,
    )


@router.get("/classes", response_class=HTMLResponse)
def class_index(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
    rows = _service(request).list_class_summaries()
    arrears_by_class: dict[int, int] = {}
    arrears_service = getattr(request.app.state, "arrears", None)
    if arrears_service is not None:
        for line in arrears_service.arrears_report():
            arrears_by_class[line.student.class_id] = (
                arrears_by_class.get(line.student.class_id, 0) + line.owed_cents
            )
    for row in rows:
        row.arrears_cents = arrears_by_class.get(row.cls.id, 0)
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/index.html",
        context={
            "rows": rows,
            "msg": request.query_params.get("msg", ""),
        },
    )


@router.get("/classes/new", response_class=HTMLResponse)
def new_class_form(request: Request, _user: User = Depends(require_admin)) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="classes/form.html",
        context={
            "action": "/classes",
            "name": "",
            "status": "",
            "status_options": _status_options(),
            "template_options": _template_options(request),
            "default_template_id": "",
            "error": "",
        },
    )


@router.post("/classes", response_class=HTMLResponse)
def create_class(
    request: Request,
    name: str = Form(""),
    status: str = Form("active"),
    default_template_id: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        template_id = _coerce_template_id(default_template_id)
        cls = _service(request).create_class(
            user=user,
            name=name,
            status=status,
            default_template_id=template_id,
        )
    except ClassError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="classes/form.html",
            context={
                "action": "/classes",
                "name": name,
                "status": status,
                "status_options": _status_options(),
                "template_options": _template_options(request),
                "default_template_id": default_template_id,
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
        error=request.query_params.get("err", ""),
    )


@router.post("/classes/{class_id}/edit", response_class=HTMLResponse)
def edit_class(
    request: Request,
    class_id: int,
    name: str = Form(""),
    status: str = Form(""),
    default_template_id: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        template_id = _coerce_template_id(default_template_id)
        service = _service(request)
        # Validate the template pick before applying the rename so a bad pick
        # can never partially apply the class's other fields.
        if template_id is not None:
            current = service.get_class(class_id).default_template_id
            if template_id not in _valid_template_ids(request, current):
                raise ClassError("Choose a valid fee template.")
        cls = service.update_class(user=user, class_id=class_id, name=name, status=status)
        service.set_default_template(
            user=user, class_id=class_id, default_template_id=template_id
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
            default_template_id=default_template_id,
        )
    return _redirect_detail(cls.id, "Class updated.")

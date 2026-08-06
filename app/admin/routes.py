"""Admin routes: staff-account management and the settings page.

Thin adapters over :class:`app.admin.service.AdminUserService`. The settings
page (``GET /admin``) is Admin-only and hosts the user-management card, the
backups card, and the shutdown form. Creating a user, disabling, re-enabling,
and resetting a password all post over htmx and re-render the users card (toast
on success, error alert on failure), with a plain-redirect fallback for
non-htmx clients. Business rules live in the service — these routes only
translate form data, errors, and templates.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin
from ..config import settings
from ..models import User
from .service import (
    USER_ROLE_LABELS,
    AdminUserError,
    AdminUserService,
)

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> AdminUserService:
    service = request.app.state.admin
    assert isinstance(service, AdminUserService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _toast_headers(message: str, tone: str = "success") -> dict[str, str]:
    return {"HX-Trigger": json.dumps({"toast": {"message": message, "tone": tone}})}


def _users_context(
    request: Request, *, error: str = "", form: dict[str, str] | None = None
) -> dict[str, object]:
    return {
        "users": _service(request).list_users(),
        "roles": USER_ROLE_LABELS,
        "error": error,
        "form": form or {},
    }


def _users_response(
    request: Request,
    *,
    error: str = "",
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/_users.html",
        context=_users_context(request, error=error, form=form),
        headers=headers,
    )


def _backups_context(request: Request, *, error: str = "") -> dict[str, object]:
    system = request.app.state.system
    return {
        "backups": system.list_backups(),
        "backup_available": system.backups_available,
        "backup_keep": settings.BACKUP_KEEP,
        "error": error,
    }


@router.get("/admin", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: User = Depends(require_admin),
) -> HTMLResponse:
    context = _users_context(
        request, error=request.query_params.get("err", "")
    )
    context.update(
        {
            "msg": request.query_params.get("msg", ""),
            **_backups_context(request),
        }
    )
    return _templates(request).TemplateResponse(
        request=request,
        name="admin/index.html",
        context=context,
    )


@router.post("/admin/users", response_class=HTMLResponse)
def create_user(
    request: Request,
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    form = {"name": name, "username": username, "role": role}
    try:
        created = _service(request).create_user(
            actor=user, name=name, username=username, password=password, role=role
        )
    except AdminUserError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return _users_response(request, error=str(exc), form=form)
    message = f"Created {USER_ROLE_LABELS[created.role]} account {created.username}."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': message})}", status_code=303
        )
    return _users_response(request, headers=_toast_headers(message))


@router.post("/admin/users/{user_id}/disable", response_class=HTMLResponse)
def disable_user(
    request: Request,
    user_id: int,
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_user(
        request,
        user,
        action=lambda svc: svc.disable_user(actor=user, user_id=user_id),
        success="Account disabled.",
    )


@router.post("/admin/users/{user_id}/enable", response_class=HTMLResponse)
def enable_user(
    request: Request,
    user_id: int,
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_user(
        request,
        user,
        action=lambda svc: svc.enable_user(actor=user, user_id=user_id),
        success="Account enabled.",
    )


@router.post("/admin/users/{user_id}/password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    user_id: int,
    password: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    return _mutate_user(
        request,
        user,
        action=lambda svc: svc.reset_password(
            actor=user, user_id=user_id, password=password
        ),
        success="Password reset.",
    )


def _mutate_user(
    request: Request,
    user: User,
    *,
    action,
    success,
) -> Response:
    try:
        action(_service(request))
    except AdminUserError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return _users_response(request, error=str(exc))
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': success})}", status_code=303
        )
    return _users_response(request, headers=_toast_headers(success))

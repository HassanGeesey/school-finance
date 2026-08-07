"""System routes: manual backup and in-app shutdown.

Thin adapters over :class:`app.system.service.SystemService`. The "Backup now"
action posts over htmx and re-renders the backups card (toast on success, error
alert on failure), with a plain-redirect fallback for non-htmx clients. The
shutdown action is a plain form POST guarded by the confirm dialog; it audits
the request, asks the server to stop, and returns a small standalone page.
Business rules live in the service — these routes only translate input, errors,
and templates.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin
from ..config import settings
from ..models import User
from .service import BackupError, SystemService

router = APIRouter(include_in_schema=False)


def _system(request: Request) -> SystemService:
    service = request.app.state.system
    assert isinstance(service, SystemService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _toast_headers(message: str, tone: str = "success") -> dict[str, str]:
    return {"HX-Trigger": json.dumps({"toast": {"message": message, "tone": tone}})}


def _backups_context(request: Request, *, error: str = "") -> dict[str, object]:
    system = _system(request)
    return {
        "backups": system.list_backups(),
        "backup_available": system.backups_available,
        "backup_keep": settings.BACKUP_KEEP,
        "error": error,
    }


def _backups_response(
    request: Request, *, error: str = "", headers: dict[str, str] | None = None
) -> Response:
    return _templates(request).TemplateResponse(
        request=request,
        name="system/_backups.html",
        context=_backups_context(request, error=error),
        headers=headers,
    )


@router.post("/system/backup", response_class=HTMLResponse)
def backup_now(
    request: Request,
    user: User = Depends(require_admin),
) -> Response:
    try:
        path = _system(request).backup_now(user=user)
    except BackupError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return _backups_response(request, error=str(exc))
    message = f"Backup created: {path.name}"
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': message})}", status_code=303
        )
    return _backups_response(request, headers=_toast_headers(message))


@router.post("/system/shutdown", response_class=HTMLResponse)
def shutdown(
    request: Request,
    user: User = Depends(require_admin),
) -> HTMLResponse:
    if settings.DISABLE_SHUTDOWN:
        return _templates(request).TemplateResponse(
            request=request,
            name="system/shutdown_disabled.html",
            context={},
            status_code=403,
        )
    _system(request).request_shutdown(user=user)
    return _templates(request).TemplateResponse(
        request=request,
        name="system/shutdown.html",
        context={},
    )

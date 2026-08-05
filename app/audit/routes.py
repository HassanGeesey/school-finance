"""Audit routes: admin browsing of the append-only log. Thin adapters over AuditService.

There is deliberately no route that creates, edits, or deletes an audit entry —
the log is written only by the service layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin
from ..models import User
from .service import AuditActions, AuditService

router = APIRouter(include_in_schema=False)

PAGE_SIZE = 50


def _audit(request: Request) -> AuditService:
    audit = request.app.state.audit
    assert isinstance(audit, AuditService)
    return audit


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


@router.get("/audit", response_class=HTMLResponse)
def audit_log(
    request: Request,
    _user: User = Depends(require_admin),
    action: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    audit = _audit(request)
    page = max(page, 1)
    offset = (page - 1) * PAGE_SIZE
    entries = audit.list_entries(action=action or None, limit=PAGE_SIZE, offset=offset)
    total = audit.count(action=action or None)
    return _templates(request).TemplateResponse(
        request=request,
        name="audit/index.html",
        context={
            "entries": entries,
            "actions": audit.list_actions(),
            "action_labels": AuditActions.LABELS,
            "action": action or "",
            "page": page,
            "page_size": PAGE_SIZE,
            "total": total,
        },
    )

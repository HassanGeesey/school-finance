"""Arrears routes: the outstanding-money report page.

Thin adapter over :class:`app.arrears.service.ArrearsService`. The report is
read-only and open to any logged-in user — the office (Admin or Finance
officer) uses it to chase unpaid fees. Business rules (what counts as arrears,
how the debt age is measured and banded) live in the service; this route only
assembles the summary stats and renders the template.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_login
from ..models import User
from .service import AGE_BAND_LATE, AGE_BAND_OVERDUE, ArrearsService

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> ArrearsService:
    service = request.app.state.arrears
    assert isinstance(service, ArrearsService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


@router.get("/arrears", response_class=HTMLResponse)
def arrears_page(
    request: Request,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """The arrears report: every owing student, amount owed, and debt age."""
    lines = _service(request).arrears_report()
    return _templates(request).TemplateResponse(
        request=request,
        name="arrears/index.html",
        context={
            "lines": lines,
            "student_count": len(lines),
            "total_cents": sum(line.owed_cents for line in lines),
            "late_count": sum(1 for line in lines if line.age_band == AGE_BAND_LATE),
            "overdue_count": sum(1 for line in lines if line.age_band == AGE_BAND_OVERDUE),
        },
    )

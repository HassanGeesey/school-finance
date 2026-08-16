"""Profile routes: the settings card editor, logo upload/removal, logo serving.

Thin adapters over :class:`app.profile.service.ProfileService`. The "School
profile" card lives on the Settings page (``GET /admin``) and is re-rendered
over htmx after each POST (toast on success, error alert on failure), with a
plain-redirect fallback for non-htmx clients. The logo file itself is served
from ``/logos/{filename}``, but only when the filename matches the current
profile — arbitrary files in the data directory are never exposed.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin
from ..models import User
from .service import LogoError, ProfileError, ProfileService, logo_url_for

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> ProfileService:
    service = request.app.state.profile
    assert isinstance(service, ProfileService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _toast_headers(message: str, tone: str = "success") -> dict[str, str]:
    return {"HX-Trigger": json.dumps({"toast": {"message": message, "tone": tone}})}


def profile_context(
    request: Request, *, error: str = "", form: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Context for the profile partial — shared with the Settings page."""
    service = _service(request)
    profile = service.get_profile()
    if profile is None:
        raise HTTPException(
            status_code=403, detail="No campus profile is available in this context."
        )
    return {
        "profile": profile,
        "current_logo_url": logo_url_for(profile),
        "error": error,
        "form": form or {},
    }


def profile_response(
    request: Request,
    *,
    error: str = "",
    form: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    return _templates(request).TemplateResponse(
        request=request,
        name="profile/_profile.html",
        context=profile_context(request, error=error, form=form),
        headers=headers,
    )


@router.post("/profile", response_class=HTMLResponse)
def update_profile(
    request: Request,
    school_name: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    form = {
        "school_name": school_name,
        "address": address,
        "phone": phone,
        "email": email,
        "website": website,
    }
    try:
        _service(request).update_profile(
            user=user,
            school_name=school_name,
            address=address,
            phone=phone,
            email=email,
            website=website,
        )
    except ProfileError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return profile_response(request, error=str(exc), form=form)
    message = "School profile saved."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': message})}", status_code=303
        )
    return profile_response(request, headers=_toast_headers(message))


@router.post("/profile/logo", response_class=HTMLResponse)
def upload_logo(
    request: Request,
    logo: UploadFile = File(...),
    user: User = Depends(require_admin),
) -> Response:
    data = logo.file.read() if logo.file is not None else b""
    try:
        filename = _service(request).save_logo(
            user=user, data=data, source_name=logo.filename or ""
        )
    except (LogoError, ProfileError) as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return profile_response(request, error=str(exc))
    message = f"Logo uploaded ({filename})."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': message})}", status_code=303
        )
    return profile_response(request, headers=_toast_headers(message))


@router.post("/profile/logo/remove", response_class=HTMLResponse)
def remove_logo(
    request: Request,
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).remove_logo(user=user)
    except LogoError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/admin?{urlencode({'err': str(exc)})}", status_code=303
            )
        return profile_response(request, error=str(exc))
    message = "Logo removed."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/admin?{urlencode({'msg': message})}", status_code=303
        )
    return profile_response(request, headers=_toast_headers(message))


@router.get("/logos/{filename}")
def logo_file(filename: str, request: Request) -> Response:
    """Serve the current logo file. Only the stored filename is exposed."""
    service = _service(request)
    profile = service.get_profile()
    if profile is None or profile.logo_filename != filename:
        raise HTTPException(status_code=404, detail="Not found")
    path = service.logo_path()
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type=service.logo_media_type())

"""Auth routes: setup wizard, login, logout. Thin adapters over AuthService."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from .service import (
    AuthError,
    AuthService,
    safe_post_login_target,
    session_max_age_seconds,
)

router = APIRouter(include_in_schema=False)


def _auth(request: Request) -> AuthService:
    auth = request.app.state.auth
    assert isinstance(auth, AuthService)
    return auth


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def _attach_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE,
        token,
        max_age=session_max_age_seconds(),
        httponly=True,
        samesite="lax",
        secure=secure,
    )


@router.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request) -> Response:
    if request.state.user is not None:
        return RedirectResponse("/", status_code=303)
    if _auth(request).has_users():
        return _redirect_login()
    return _templates(request).TemplateResponse(
        request=request,
        name="auth/setup.html",
        context={"school_name": "", "name": "", "username": ""},
    )


@router.post("/setup", response_class=HTMLResponse)
def setup_submit(
    request: Request,
    school_name: str = Form(""),
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
) -> Response:
    auth = _auth(request)
    try:
        if settings.CLOUD_MODE:
            auth.setup_school_superadmin(
                school_name=school_name, name=name, username=username, password=password
            )
        else:
            auth.setup_first_admin(
                school_name=school_name, name=name, username=username, password=password
            )
    except AuthError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={
                "error": str(exc),
                "school_name": school_name,
                "name": name,
                "username": username,
            },
            status_code=400,
        )
    # The first admin is created; the app now requires login.
    return _redirect_login()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/") -> Response:
    if request.state.user is not None:
        return RedirectResponse("/", status_code=303)
    if not _auth(request).has_users():
        return RedirectResponse("/setup", status_code=303)
    return _templates(request).TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"next": safe_post_login_target(next)},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
) -> Response:
    user_and_token = _auth(request).login(username, password)
    if user_and_token is None:
        return _templates(request).TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "next": safe_post_login_target(next),
                "username": username,
                "error": "Invalid username or password.",
            },
            status_code=400,
        )
    _user, token = user_and_token
    response = RedirectResponse(safe_post_login_target(next), status_code=303)
    # Behind a TLS-terminating proxy (Traefik), forward the X-Forwarded-Proto
    # header and mark the session cookie Secure; plain-HTTP installs (the EXE
    # on localhost) get no such header and stay on plain cookies.
    secure = request.headers.get("x-forwarded-proto") == "https"
    _attach_session_cookie(response, token, secure=secure)
    return response


@router.post("/logout")
def logout(request: Request) -> Response:
    token = request.cookies.get(settings.SESSION_COOKIE)
    if token:
        _auth(request).destroy_session(token)
    response = _redirect_login()
    response.delete_cookie(settings.SESSION_COOKIE)
    return response

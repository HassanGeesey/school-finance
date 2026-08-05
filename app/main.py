"""FastAPI application factory.

The single entry point: creates the engine/session wiring, mounts static assets,
registers the base layout, and exposes the app. Feature routers are mounted here
as they land.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from jinja2.runtime import Context

from .auth.deps import require_admin, require_login
from .auth.routes import router as auth_router
from .auth.service import AuthService
from .config import settings
from .db import Database, make_engine
from .models import User, UserRoles

ROLE_LABELS = {
    UserRoles.ADMIN: "Admin",
    UserRoles.FINANCE: "Finance officer",
}


def _register_template_globals(templates: Jinja2Templates) -> None:
    @pass_context
    def current_user(context: Context) -> User | None:
        request = context.get("request")
        if request is None:
            return None
        return getattr(request.state, "user", None)

    def role_label(role: str) -> str:
        return ROLE_LABELS.get(role, role)

    templates.env.globals.update(
        app_name=settings.APP_NAME,
        app_version=settings.VERSION,
        year=datetime.now(timezone.utc).year,
        current_user=current_user,
        role_label=role_label,
    )


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or settings.DATABASE_URL

    # The default file-backed database needs its data directory to exist.
    if url == settings.DATABASE_URL:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(make_engine(url))
    auth = AuthService(db)
    templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))
    _register_template_globals(templates)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.create_all()
        yield

    app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
    app.state.db = db
    app.state.auth = auth
    app.state.templates = templates

    @app.middleware("http")
    async def resolve_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.user = None
        token = request.cookies.get(settings.SESSION_COOKIE)
        if token:
            request.state.user = auth.user_for_token(token)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
    app.include_router(auth_router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"database_url": url},
        )

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    def admin_page(request: Request, _user: User = Depends(require_admin)) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={},
        )

    return app


app = create_app()

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

from .audit.routes import router as audit_router
from .audit.service import AuditService
from .arrears.routes import router as arrears_router
from .arrears.service import ArrearsService
from .auth.deps import require_admin, require_login
from .auth.routes import router as auth_router
from .auth.service import AuthService
from .classes.routes import router as classes_router
from .classes.service import CLASS_STATUS_LABELS, ClassService
from .config import settings
from .db import Database, make_engine
from .expenses.routes import router as expenses_router
from .expenses.service import ExpenseService
from .fees.account_routes import router as account_router
from .fees.routes import router as fees_router
from .fees.service import AdjustmentsService, FeeService
from .models import User, UserRoles
from .money import format_cents, format_input_cents
from .payments.routes import router as payments_router
from .payments.service import PaymentService
from .reports.routes import dashboard_context, router as reports_router
from .reports.service import ReportService
from .students.routes import router as students_router
from .students.service import StudentService

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

    def class_status_label(status: str) -> str:
        return CLASS_STATUS_LABELS.get(status, status)

    templates.env.globals.update(
        app_name=settings.APP_NAME,
        app_version=settings.VERSION,
        year=datetime.now(timezone.utc).year,
        current_user=current_user,
        role_label=role_label,
        class_status_label=class_status_label,
        money=format_cents,
        money_input=format_input_cents,
    )


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or settings.DATABASE_URL

    # The default file-backed database needs its data directory to exist.
    if url == settings.DATABASE_URL:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(make_engine(url))
    audit = AuditService(db)
    auth = AuthService(db, audit=audit)
    classes = ClassService(db, audit=audit)
    students = StudentService(db, audit=audit)
    fees = FeeService(db, audit=audit)
    adjustments = AdjustmentsService(db, audit=audit)
    payments = PaymentService(db, audit=audit)
    expenses = ExpenseService(db, audit=audit)
    arrears = ArrearsService(db)
    reports = ReportService(db, arrears=arrears)
    templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))
    _register_template_globals(templates)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.create_all()
        yield

    app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
    app.state.db = db
    app.state.auth = auth
    app.state.audit = audit
    app.state.classes = classes
    app.state.students = students
    app.state.fees = fees
    app.state.adjustments = adjustments
    app.state.payments = payments
    app.state.expenses = expenses
    app.state.arrears = arrears
    app.state.reports = reports
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
    app.include_router(audit_router)
    app.include_router(classes_router)
    app.include_router(students_router)
    app.include_router(fees_router)
    app.include_router(account_router)
    app.include_router(payments_router)
    app.include_router(expenses_router)
    app.include_router(arrears_router)
    app.include_router(reports_router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
        context = dashboard_context(request)
        context["database_url"] = url
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context=context,
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

"""FastAPI application factory.

The single entry point: creates the engine/session wiring, mounts static assets,
registers the base layout, and exposes the app. Feature routers are mounted here
as they land.

``include_billing=False`` builds a test mini-app that skips the not-yet-reworked
billing modules (payments/arrears/reports still reference removed models until
their own rework tickets land) — the owned fee/class tests run against this
smaller surface.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .admin.routes import router as admin_router
from .admin.service import AdminUserService
from .audit.routes import router as audit_router
from .audit.service import AuditService
from .auth.deps import require_login
from .auth.routes import router as auth_router
from .auth.service import AuthService
from .classes.routes import router as classes_router
from .classes.service import ClassService
from .config import settings
from .db import Database, make_engine
from .expenses.routes import router as expenses_router
from .expenses.service import ExpenseService
from .fees.routes import router as fees_router
from .fees.service import ClosedMonthService, TemplateService, WaiverService
from .models import User
from .profile.routes import router as profile_router
from .profile.service import LogoStorage, ProfileService
from .students.routes import router as students_router
from .students.service import StudentService
from .system.routes import router as system_router
from .system.service import BackupService, SystemService, uvicorn_stop
from .templating import build_templates
from .tenants.service import TenantService


def create_app(
    database_url: str | None = None,
    *,
    include_billing: bool = True,
    shutdown_stopper: Callable[[], None] | None = None,
    backup_source: Path | None = None,
    backup_dir: Path | None = None,
    logo_dir: Path | None = None,
) -> FastAPI:
    url = database_url or settings.DATABASE_URL

    # The default file-backed database needs its data directory to exist.
    if url == settings.DATABASE_URL:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(make_engine(url))
    audit = AuditService(db)
    # The default logo location is next to the app data (docs/adr/0001): the
    # file is written as ``<data>/logo.<ext>``. Tests (in-memory URL) inject a
    # temp directory explicitly — otherwise logo storage is unavailable so
    # nothing can be written to the real data folder.
    logos = None
    if logo_dir is not None or url == settings.DATABASE_URL:
        logos = LogoStorage(logo_dir or settings.DATA_DIR)
    profile = ProfileService(db, audit=audit, logos=logos)
    auth = AuthService(db, audit=audit, profile=profile)
    classes = ClassService(db, audit=audit)
    students = StudentService(db, audit=audit)
    fees = TemplateService(db, audit=audit)
    fees_closed = ClosedMonthService(db, audit=audit)
    waivers = WaiverService(db, audit=audit)
    expenses = ExpenseService(db, audit=audit)
    admin = AdminUserService(db, audit=audit)
    tenants = TenantService(db)
    templates = build_templates(settings.TEMPLATES_DIR)

    # Backups only make sense against the real SQLite file. In-memory databases
    # (tests) skip the backup service entirely; tests can inject a temp source.
    source = backup_source
    if source is None and url == settings.DATABASE_URL:
        source = settings.DB_PATH
    backups = None
    if source is not None:
        backups = BackupService(
            source_path=source,
            backup_dir=backup_dir or (settings.DATA_DIR / "backups"),
            keep=settings.BACKUP_KEEP,
        )
    # The default stopper stops a real uvicorn server; test apps get a no-op so
    # a test that hits the shutdown route can never stop the test runner.
    stopper = shutdown_stopper
    if stopper is None and url == settings.DATABASE_URL:
        stopper = uvicorn_stop
    system = SystemService(db, audit=audit, backups=backups, stopper=stopper)

    # The billing features (payments/arrears/reports) are being reworked ticket
    # by ticket; their old modules still import removed models, so the mini test
    # app skips them until the rework lands.
    dashboard_builder: Callable[[Request], dict[str, object]] | None = None
    if include_billing:
        from .arrears.routes import router as arrears_router
        from .arrears.service import ArrearsService
        from .payments.routes import router as payments_router
        from .payments.service import PaymentService
        from .reports.routes import dashboard_context, router as reports_router
        from .reports.service import ReportService

        payments = PaymentService(db, audit=audit)
        arrears = ArrearsService(db)
        reports = ReportService(db, arrears=arrears)
        dashboard_builder = dashboard_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.create_all()
        tenants.ensure_bootstrap()
        system.backup_on_startup()
        yield

    app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
    app.state.db = db
    app.state.auth = auth
    app.state.audit = audit
    app.state.classes = classes
    app.state.students = students
    app.state.fees = fees
    app.state.fees_closed = fees_closed
    app.state.waivers = waivers
    app.state.expenses = expenses
    app.state.admin = admin
    app.state.profile = profile
    app.state.system = system
    app.state.tenants = tenants
    app.state.templates = templates
    if include_billing:
        app.state.payments = payments
        app.state.arrears = arrears
        app.state.reports = reports

    @app.middleware("http")
    async def resolve_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.user = None
        token = request.cookies.get(settings.SESSION_COOKIE)
        if token:
            request.state.user = auth.user_for_token(token)
        request.state.school_profile = profile.get_profile()
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(admin_router)
    app.include_router(classes_router)
    app.include_router(students_router)
    app.include_router(fees_router)
    app.include_router(expenses_router)
    app.include_router(profile_router)
    app.include_router(system_router)
    if include_billing:
        app.include_router(payments_router)
        app.include_router(arrears_router)
        app.include_router(reports_router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request, _user: User = Depends(require_login)) -> HTMLResponse:
        context = dashboard_builder(request) if dashboard_builder is not None else {}
        context["database_url"] = url
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context=context,
        )

    return app


# No module-level ``app = create_app()``: the billing modules are still being
# reworked ticket by ticket, so the full app cannot start yet (ticket 01). Start
# it as a factory when the rework lands: ``uvicorn "app.main:create_app" --factory``.

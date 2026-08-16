"""School Dashboard routes (multi-school ticket 08): the Superadmin's working
surface and the Owner's read-only view.

Thin adapters over :class:`app.schools.service.SchoolDashboardService`.
``GET /school`` is the School Dashboard (Campuses with per-Campus KPI cards,
Campus management, and Owner accounts); every management POST is Superadmin-only
and every mutation the middleware refuses for School-bound accounts. The
``/campuses/{id}/...`` routes are the read-only drill-down: a Superadmin or
Owner opens any Campus's existing pages (dashboard, students, classes, fees,
payments, expenses, arrears, reports) by running the Campus's own page handlers
under a Campus-scoped context, so each page shows exactly that Campus's data and
nothing is ever written.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_school_bound, require_superadmin
from ..models import Campus, User, UserRoles
from ..tenants.scope import RequestScope, scope_context
from .service import CampusNotFound, SchoolError, SchoolDashboardService

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> SchoolDashboardService:
    service = request.app.state.schools
    assert isinstance(service, SchoolDashboardService)
    return service


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _campus_or_404(request: Request, campus_id: int) -> Campus:
    try:
        return _service(request).get_campus(campus_id)
    except CampusNotFound:
        raise HTTPException(status_code=404, detail="Campus not found.") from None


def _under_campus(request: Request, campus: Campus, handler: Callable[[Request], Response]):
    """Run a Campus page handler with the request scoped to that Campus.

    The acting user stays the School-bound viewer; only the tenant scope and the
    Campus branding follow the viewed Campus, so the page renders exactly that
    branch's data and reads/writes are never possible outside it.
    """
    user: User = request.state.user
    campus_scope = RequestScope(user=user, school_id=user.school_id, campus_id=campus.id)
    with scope_context(campus_scope):
        request.state.campus_profile = request.app.state.profile.get_profile()
        return handler(request)


def _redirect_school(msg_or_err: str, *, err: bool = False) -> RedirectResponse:
    params = {"err": msg_or_err} if err else {"msg": msg_or_err}
    return RedirectResponse(f"/school?{urlencode(params)}", status_code=303)


# ---------------------------------------------------------------------------
# School Dashboard
# ---------------------------------------------------------------------------


@router.get("/school", response_class=HTMLResponse)
def school_dashboard(
    request: Request,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    service = _service(request)
    user: User = request.state.user
    is_superadmin = user.role == UserRoles.SUPERADMIN
    return _templates(request).TemplateResponse(
        request=request,
        name="school/dashboard.html",
        context={
            "school": service.school(),
            "campuses": service.list_campuses(),
            "owners": service.list_owners() if is_superadmin else [],
            "is_superadmin": is_superadmin,
            "has_reporting": getattr(request.app.state, "reports", None) is not None,
            "msg": request.query_params.get("msg", ""),
            "err": request.query_params.get("err", ""),
        },
    )


@router.get("/school/campuses/new", response_class=HTMLResponse)
def new_campus_form(
    request: Request,
    _user: User = Depends(require_superadmin),
) -> HTMLResponse:
    return _templates(request).TemplateResponse(
        request=request,
        name="school/campus_form.html",
        context={"error": "", "form": {}},
    )


@router.post("/school/campuses", response_class=HTMLResponse)
def create_campus(
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    admin_name: str = Form(""),
    admin_username: str = Form(""),
    admin_password: str = Form(""),
    user: User = Depends(require_superadmin),
) -> Response:
    form = {
        "name": name,
        "address": address,
        "phone": phone,
        "email": email,
        "website": website,
        "admin_name": admin_name,
        "admin_username": admin_username,
    }
    try:
        _service(request).create_campus(
            actor=user,
            name=name,
            address=address,
            phone=phone,
            email=email,
            website=website,
            admin_name=admin_name,
            admin_username=admin_username,
            admin_password=admin_password,
        )
    except SchoolError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="school/campus_form.html",
            context={"error": str(exc), "form": form},
            status_code=400,
        )
    message = f"Campus '{name.strip()}' created."
    return RedirectResponse(
        f"/school?{urlencode({'msg': message})}", status_code=303
    )


@router.post("/school/campuses/{campus_id}/admin", response_class=HTMLResponse)
def assign_campus_admin(
    request: Request,
    campus_id: int,
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    user: User = Depends(require_superadmin),
) -> Response:
    try:
        admin = _service(request).create_campus_admin(
            actor=user, campus_id=campus_id, name=name, username=username, password=password
        )
    except (CampusNotFound, SchoolError) as exc:
        return _redirect_school(str(exc), err=True)
    return _redirect_school(f"Campus admin {admin.username} assigned.")


@router.post("/school/campuses/{campus_id}/archive", response_class=HTMLResponse)
def archive_campus(
    request: Request,
    campus_id: int,
    user: User = Depends(require_superadmin),
) -> Response:
    try:
        campus = _service(request).archive_campus(actor=user, campus_id=campus_id)
    except (CampusNotFound, SchoolError) as exc:
        return _redirect_school(str(exc), err=True)
    return _redirect_school(f"Campus '{campus.name}' archived.")


@router.post("/school/owners", response_class=HTMLResponse)
def create_owner(
    request: Request,
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    user: User = Depends(require_superadmin),
) -> Response:
    try:
        owner = _service(request).create_owner(actor=user, name=name, username=username, password=password)
    except SchoolError as exc:
        return _redirect_school(str(exc), err=True)
    return _redirect_school(f"Owner account {owner.username} created.")


@router.post("/school/owners/{user_id}/disable", response_class=HTMLResponse)
def disable_owner(
    request: Request,
    user_id: int,
    user: User = Depends(require_superadmin),
) -> Response:
    try:
        owner = _service(request).disable_owner(actor=user, user_id=user_id)
    except SchoolError as exc:
        return _redirect_school(str(exc), err=True)
    return _redirect_school(f"Owner account {owner.username} disabled.")


@router.post("/school/owners/{user_id}/enable", response_class=HTMLResponse)
def enable_owner(
    request: Request,
    user_id: int,
    user: User = Depends(require_superadmin),
) -> Response:
    try:
        owner = _service(request).enable_owner(actor=user, user_id=user_id)
    except SchoolError as exc:
        return _redirect_school(str(exc), err=True)
    return _redirect_school(f"Owner account {owner.username} enabled.")


# ---------------------------------------------------------------------------
# Read-only drill-down: a School-bound viewer opening one Campus's pages
# ---------------------------------------------------------------------------


@router.get("/campuses/{campus_id}", response_class=HTMLResponse)
def campus_dashboard(
    request: Request,
    campus_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..reports.routes import dashboard_context

    campus = _campus_or_404(request, campus_id)
    return _under_campus(
        request,
        campus,
        lambda req: _templates(req).TemplateResponse(
            request=req,
            name="home.html",
            context={
                **dashboard_context(req),
                "read_only": True,
                "campus": campus,
                "is_superadmin": req.state.user.role == UserRoles.SUPERADMIN,
            },
        ),
    )


@router.get("/campuses/{campus_id}/students", response_class=HTMLResponse)
def campus_students(
    request: Request,
    campus_id: int,
    q: str = "",
    class_id: str = "",
    period: str = "",
    status: str = "",
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..students.routes import search_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(
        request,
        campus,
        lambda req: search_page(req, q=q, class_id=class_id, period=period, status=status),
    )


@router.get("/campuses/{campus_id}/students/{student_id}/account", response_class=HTMLResponse)
def campus_student_account(
    request: Request,
    campus_id: int,
    student_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..students.routes import student_account_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(
        request, campus, lambda req: student_account_page(req, student_id=student_id)
    )


@router.get("/campuses/{campus_id}/classes", response_class=HTMLResponse)
def campus_classes(
    request: Request,
    campus_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..classes.routes import class_index

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, class_index)


@router.get("/campuses/{campus_id}/classes/{class_id}", response_class=HTMLResponse)
def campus_class_detail(
    request: Request,
    campus_id: int,
    class_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..classes.routes import class_detail

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, lambda req: class_detail(req, class_id=class_id))


@router.get("/campuses/{campus_id}/fees", response_class=HTMLResponse)
def campus_fees(
    request: Request,
    campus_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..fees.routes import fees_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, fees_page)


@router.get("/campuses/{campus_id}/payments", response_class=HTMLResponse)
def campus_payments(
    request: Request,
    campus_id: int,
    q: str = "",
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..payments.routes import payments_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, lambda req: payments_page(req, q=q))


@router.get("/campuses/{campus_id}/expenses", response_class=HTMLResponse)
def campus_expenses(
    request: Request,
    campus_id: int,
    category: str = "",
    period: str = "",
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..expenses.routes import expenses_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(
        request,
        campus,
        lambda req: expenses_page(req, category=category, period=period, user=req.state.user),
    )


@router.get("/campuses/{campus_id}/arrears", response_class=HTMLResponse)
def campus_arrears(
    request: Request,
    campus_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..arrears.routes import arrears_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, arrears_page)


@router.get("/campuses/{campus_id}/reports", response_class=HTMLResponse)
def campus_reports(
    request: Request,
    campus_id: int,
    _user: User = Depends(require_school_bound),
) -> HTMLResponse:
    from ..reports.routes import reports_page

    campus = _campus_or_404(request, campus_id)
    return _under_campus(request, campus, reports_page)


def _campus_report(
    request: Request,
    campus_id: int,
    page_name: str,
    *,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    class_id: int | None = None,
) -> Response:
    from ..reports.routes import (
        expense_category_csv,
        expense_category_page,
        income_expense_csv,
        income_expense_page,
        paid_students_csv,
        paid_students_page,
        students_csv,
        students_page,
        summary_csv,
        summary_page,
    )

    def run_with(csv_suffix: bool, req: Request):
        if page_name == "income-expense":
            handler = income_expense_csv if csv_suffix else income_expense_page
            return handler(req, period=period, month=month, year=year)
        if page_name == "expense-category":
            handler = expense_category_csv if csv_suffix else expense_category_page
            return handler(req, period=period, month=month, year=year)
        if page_name == "paid-students":
            handler = paid_students_csv if csv_suffix else paid_students_page
            return handler(req, period=period, month=month, year=year, class_id=class_id)
        if page_name == "summary":
            handler = summary_csv if csv_suffix else summary_page
            return handler(req, period=period, month=month, year=year)
        if page_name == "students":
            handler = students_csv if csv_suffix else students_page
            return handler(req, class_id=class_id)
        raise HTTPException(status_code=404, detail="Report not found.")

    campus = _campus_or_404(request, campus_id)
    csv_suffix = request.url.path.endswith(".csv")
    return _under_campus(request, campus, lambda req: run_with(csv_suffix, req))


@router.get("/campuses/{campus_id}/reports/{report_name}", response_class=HTMLResponse)
def campus_report_page(
    request: Request,
    campus_id: int,
    report_name: str,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    class_id: int | None = None,
    _user: User = Depends(require_school_bound),
) -> Response:
    return _campus_report(
        request,
        campus_id,
        report_name,
        period=period,
        month=month,
        year=year,
        class_id=class_id,
    )


@router.get("/campuses/{campus_id}/reports/{report_name}.csv")
def campus_report_csv(
    request: Request,
    campus_id: int,
    report_name: str,
    period: str = "",
    month: int | None = None,
    year: int | None = None,
    class_id: int | None = None,
    _user: User = Depends(require_school_bound),
) -> Response:
    return _campus_report(
        request,
        campus_id,
        report_name,
        period=period,
        month=month,
        year=year,
        class_id=class_id,
    )

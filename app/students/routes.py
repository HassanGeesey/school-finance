"""Student routes: add, edit, archive/restore, search, and CSV import.

Thin adapters over :class:`app.students.service.StudentService`. Viewing
(reading the class page's student list, the search page) is open to any
logged-in user; every mutation (add, edit, archive, restore, import) is
Admin-only and audited by the service layer. The import reports what was
imported and which rows were skipped.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..charge_status import CHARGE_STATUS_LABELS, CHARGE_STATUS_TONES
from ..classes.service import ClassNotFound, ClassService
from ..fees.account import amount_in_force
from ..fees.service import (
    MONTH_NAMES,
    TemplateService,
    WaiverError,
    WaiverService,
    default_effective_month,
    period_label,
)
from ..models import User
from ..money import format_cents
from ..payments.service import PaymentService
from ..reports.service import ReportService, StudentStatusRow
from .service import StudentError, StudentImportError, StudentNotFound, StudentService

router = APIRouter(include_in_schema=False)


def _service(request: Request) -> StudentService:
    service = request.app.state.students
    assert isinstance(service, StudentService)
    return service


def _waivers(request: Request) -> WaiverService:
    service = request.app.state.waivers
    assert isinstance(service, WaiverService)
    return service


def _reports(request: Request) -> ReportService:
    service = request.app.state.reports
    assert isinstance(service, ReportService)
    return service


def _get_student(request: Request, student_id: int):
    try:
        return _service(request).get_student(student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.") from None


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    assert isinstance(templates, Jinja2Templates)
    return templates


def _redirect_class(class_id: int, msg: str) -> RedirectResponse:
    return RedirectResponse(
        f"/classes/{class_id}?{urlencode({'msg': msg})}", status_code=303
    )


def _class_options(request: Request) -> list[tuple[int, str]]:
    service = request.app.state.classes
    assert isinstance(service, ClassService)
    return [
        (summary.cls.id, summary.cls.name)
        for summary in service.list_class_summaries()
    ]


def _coerce_class_id(raw: str) -> int | None:
    """Empty string means "All classes" (matches the fees page)."""
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ClassNotFound("Choose a class.") from None


def _coerce_template_id(raw: str) -> int | None:
    """A posted template picker value, or ``None`` when nothing was chosen."""
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise StudentError("Choose a valid fee template.") from None


def _class_default_template_id(request: Request, class_id: int) -> int | None:
    """The class's default template, which pre-fills and applies to new students."""
    classes = request.app.state.classes
    assert isinstance(classes, ClassService)
    summary = classes.class_summary(class_id)
    template = summary.cls.default_template
    return template.id if template is not None else None


def _resolve_billing_source(
    request: Request, class_id: int, fee_template_id: str, custom_amount: str
) -> tuple[int | None, str | None]:
    """Turn posted billing fields into a template id / custom amount.

    When neither is given, the class's default template applies (the form
    pre-fills with it). An unknown template id is rejected.
    """
    template_id = _coerce_template_id(fee_template_id)
    amount = (custom_amount or "").strip() or None
    if template_id is None and amount is None:
        template_id = _class_default_template_id(request, class_id)
    return template_id, amount


def _template_options(request: Request) -> list[tuple[int, str]]:
    service = request.app.state.fees
    assert isinstance(service, TemplateService)
    return [
        (template.id, f"{template.name} ({format_cents(template.amount_cents)}/month)")
        for template in service.list_active_templates()
    ]


def _edit_context(
    request: Request,
    student,
    first_name: str,
    last_name: str,
    *,
    error: str = "",
) -> dict[str, object]:
    """Context for the student edit page, including the amount-change block."""
    today = date.today()
    with request.app.state.db.session() as session:
        current_amount = amount_in_force(session, student, today.month, today.year)
    return {
        "student": student,
        "first_name": first_name,
        "last_name": last_name,
        "error": error,
        "current_amount": format_cents(current_amount),
        "template_options": _template_options(request),
        "month_options": _month_options(),
    }


def _month_options() -> list[tuple[int, int, str]]:
    """The next six calendar months (default effective month first)."""
    month, year = default_effective_month()
    options: list[tuple[int, int, str]] = []
    for _ in range(6):
        options.append((month, year, period_label(month, year)))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return options


def _coerce_effective_month(raw: str) -> tuple[int, int]:
    """A posted ``YYYY-MM`` effective month, defaulting to next month."""
    raw = (raw or "").strip()
    if raw == "":
        return default_effective_month()
    try:
        year, month = (int(part) for part in raw.split("-"))
    except (TypeError, ValueError):
        raise StudentError("Choose a valid effective month.") from None
    if not 1 <= month <= 12:
        raise StudentError("Choose a valid effective month.")
    return month, year


def _apply_billing_change(
    request: Request,
    user: User,
    student,
    fee_template_id: str,
    custom_amount: str,
    effective_month: str,
):
    """Apply an optional amount change from the edit form.

    An empty template picker and an empty custom amount mean "no billing
    change" (names-only edit). When a custom amount is given it wins over a
    picked template, matching the add-student form.
    """
    template_id = _coerce_template_id(fee_template_id)
    amount = (custom_amount or "").strip() or None
    if template_id is None and amount is None:
        return student
    month, year = _coerce_effective_month(effective_month)
    if amount is not None:
        return _service(request).change_amount(
            user=user, student_id=student.id, amount=amount, month=month, year=year
        )
    assert template_id is not None
    return _service(request).set_template(
        user=user, student_id=student.id, fee_template_id=template_id, month=month, year=year
    )


@router.get("/students", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
    class_id: str = "",
    period: str = "",
    status: str = "",
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """Search students by name, optionally narrowed to one class and a month's
    paid status. The paid column and status filter only exist once a month has
    been billed (defaulting to the most recent billed month)."""
    selected_class_id = _coerce_class_id(class_id)
    try:
        students = _service(request).search_students(q, class_id=selected_class_id)
        class_options = _class_options(request)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")

    billed_periods = _reports(request).billed_periods()
    period_options = [
        (f"{year:04d}-{month:02d}", period_label(month, year))
        for month, year in billed_periods
    ]
    period_values = {value for value, _ in period_options}
    selected_period = (
        period
        if period in period_values
        else (period_options[0][0] if period_options else "")
    )
    selected_status = status if status in CHARGE_STATUS_LABELS else ""

    if selected_period:
        selected_year, selected_month = (int(part) for part in selected_period.split("-"))
        rows = _reports(request).student_status_rows(
            students, selected_month, selected_year, status=selected_status
        )
    else:
        rows = [
            StudentStatusRow(student=student, paid_status=None, remaining_cents=0)
            for student in students
        ]
    return _templates(request).TemplateResponse(
        request=request,
        name="students/search.html",
        context={
            "rows": rows,
            "q": q,
            "class_id": selected_class_id,
            "class_options": class_options,
            "period_options": period_options,
            "selected_period": selected_period,
            "selected_status": selected_status,
            "charge_status_labels": CHARGE_STATUS_LABELS,
            "charge_status_tones": CHARGE_STATUS_TONES,
        },
    )


@router.get("/students/{student_id}/edit", response_class=HTMLResponse)
def edit_student_form(
    request: Request,
    student_id: int,
    _user: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        student = _service(request).get_student(student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/edit.html",
        context=_edit_context(
            request, student, student.first_name, student.last_name
        ),
    )


@router.post("/students/{student_id}/edit", response_class=HTMLResponse)
def edit_student(
    request: Request,
    student_id: int,
    first_name: str = Form(""),
    last_name: str = Form(""),
    fee_template_id: str = Form(""),
    custom_amount: str = Form(""),
    effective_month: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        student = _service(request).update_student(
            user=user, student_id=student_id, first_name=first_name, last_name=last_name
        )
        student = _apply_billing_change(
            request, user, student, fee_template_id, custom_amount, effective_month
        )
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.")
    except StudentError as exc:
        try:
            current = _service(request).get_student(student_id)
        except StudentNotFound:
            raise HTTPException(status_code=404, detail="Student not found.")
        return _templates(request).TemplateResponse(
            request=request,
            name="students/edit.html",
            context=_edit_context(request, current, first_name, last_name, error=str(exc)),
            status_code=400,
        )
    return _redirect_class(student.class_id, "Student updated.")


@router.post("/students/{student_id}/archive", response_class=HTMLResponse)
def archive_student(
    request: Request,
    student_id: int,
    user: User = Depends(require_admin),
) -> Response:
    try:
        student = _service(request).archive_student(user=user, student_id=student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.")
    return _redirect_class(student.class_id, "Student archived.")


@router.post("/students/{student_id}/restore", response_class=HTMLResponse)
def restore_student(
    request: Request,
    student_id: int,
    user: User = Depends(require_admin),
) -> Response:
    try:
        student = _service(request).restore_student(user=user, student_id=student_id)
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.")
    return _redirect_class(student.class_id, "Student restored.")


@router.get("/students/{student_id}/account", response_class=HTMLResponse)
def student_account_page(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """The student's account: the derived per-month comparison (ticket 07).

    Open to any logged-in user (the Finance officer chases balances too). The
    per-month rows (expected, waivers, paid, credit consumed, status), the
    running totals, the payments list, and the credit line all come from
    ``PaymentService.account_summary``; the print block on the page doubles as
    the statement.
    """
    student = _get_student(request, student_id)
    context = _account_context(request, student)
    context["msg"] = request.query_params.get("msg", "")
    context["err"] = request.query_params.get("err", "")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/account.html",
        context=context,
    )


@router.get("/students/{student_id}/account/finance", response_class=HTMLResponse)
def account_finance_partial(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """The account's finance body alone, so the page can refresh it after a
    waiver (htmx ``waivers-changed`` event)."""
    student = _get_student(request, student_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="fees/_account_finance.html",
        context=_account_context(request, student),
    )


def _account_context(request: Request, student) -> dict[str, object]:
    payments = request.app.state.payments
    assert isinstance(payments, PaymentService)
    summary = payments.account_summary(student.id)
    return {
        "student": student,
        "account": summary.account,
        "oldest_unpaid": summary.oldest_unpaid,
        "period_label": period_label,
        "charge_status_labels": CHARGE_STATUS_LABELS,
        "charge_status_tones": CHARGE_STATUS_TONES,
    }


@router.get("/students/{student_id}/waivers/new-form", response_class=HTMLResponse)
def waiver_form(
    request: Request,
    student_id: int,
    _user: User = Depends(require_login),
) -> HTMLResponse:
    """The add-waiver form, loaded into the account page's modal (htmx).

    The month picker lists the student's owed months (oldest unpaid first, or
    the first owed month by default). Both Admin and Finance officer may waive
    (FW-13), so the route is behind ``require_login`` only.
    """
    student = _get_student(request, student_id)
    return _templates(request).TemplateResponse(
        request=request,
        name="students/_waiver_form.html",
        context=_waiver_form_context(request, student),
    )


@router.post("/students/{student_id}/waivers", response_class=HTMLResponse)
def add_waiver(
    request: Request,
    student_id: int,
    period: str = Form(""),
    amount: str = Form(""),
    label: str = Form(""),
    user: User = Depends(require_login),
) -> Response:
    student = _get_student(request, student_id)
    try:
        month, year = _coerce_waiver_period(period)
        _waivers(request).add_waiver(
            user=user, student_id=student_id, month=month, year=year, amount=amount, label=label
        )
    except WaiverError as exc:
        if not _is_htmx(request):
            return RedirectResponse(
                f"/students/{student_id}/account?{urlencode({'err': str(exc)})}",
                status_code=303,
            )
        return _templates(request).TemplateResponse(
            request=request,
            name="students/_waiver_form.html",
            context=_waiver_form_context(
                request, student, amount=amount, label=label, period=period, error=str(exc)
            ),
            status_code=400,
        )
    message = "Waiver added."
    if not _is_htmx(request):
        return RedirectResponse(
            f"/students/{student_id}/account?{urlencode({'msg': message})}",
            status_code=303,
        )
    return _templates(request).TemplateResponse(
        request=request,
        name="students/_waiver_form.html",
        context=_waiver_form_context(request, student),
        headers={
            "HX-Trigger": json.dumps(
                {
                    "toast": {"message": message, "tone": "success"},
                    "waivers-changed": True,
                }
            )
        },
    )


def _coerce_waiver_period(raw: str) -> tuple[int, int]:
    """A posted ``YYYY-MM`` owed-month picker value."""
    raw = (raw or "").strip()
    try:
        year, month = (int(part) for part in raw.split("-"))
    except (TypeError, ValueError):
        raise WaiverError("Choose a valid month to waive.") from None
    if not 1 <= month <= 12:
        raise WaiverError("Choose a valid month to waive.")
    return month, year


def _waiver_form_context(
    request: Request,
    student,
    *,
    amount: str = "",
    label: str = "",
    period: str = "",
    error: str = "",
) -> dict[str, object]:
    payments = request.app.state.payments
    assert isinstance(payments, PaymentService)
    summary = payments.account_summary(student.id)
    options = [
        (line.month, line.year, line.period_label) for line in summary.account.lines
    ]
    if not options:
        today = date.today()
        options = [(today.month, today.year, period_label(today.month, today.year))]
    if summary.oldest_unpaid is not None:
        year, month = summary.oldest_unpaid
        default_period = f"{year:04d}-{month:02d}"
    else:
        default_period = f"{options[0][1]:04d}-{options[0][0]:02d}"
    return {
        "student": student,
        "month_options": options,
        "selected_period": period or default_period,
        "amount": amount,
        "label": label,
        "error": error,
    }


@router.post("/classes/{class_id}/students", response_class=HTMLResponse)
def add_student(
    request: Request,
    class_id: int,
    first_name: str = Form(""),
    last_name: str = Form(""),
    enrolled_on: str = Form(""),
    fee_template_id: str = Form(""),
    custom_amount: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        template_id, amount = _resolve_billing_source(
            request, class_id, fee_template_id, custom_amount
        )
        _service(request).add_student(
            user=user,
            class_id=class_id,
            first_name=first_name,
            last_name=last_name,
            enrolled_on=enrolled_on,
            fee_template_id=template_id,
            custom_amount=amount,
        )
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    except StudentError as exc:
        return RedirectResponse(
            f"/classes/{class_id}?{urlencode({'err': str(exc)})}", status_code=303
        )
    return _redirect_class(class_id, "Student added.")


@router.get("/classes/{class_id}/students/import", response_class=HTMLResponse)
def import_form(
    request: Request,
    class_id: int,
    _user: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        class_name = _service(request).class_name(class_id)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/import.html",
        context=_import_form_context(request, class_id, class_name),
    )


@router.post("/classes/{class_id}/students/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    class_id: int,
    file: UploadFile = File(...),
    enrolled_on: str = Form(""),
    fee_template_id: str = Form(""),
    custom_amount: str = Form(""),
    user: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        content = file.file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _import_form_response(request, class_id, error="The CSV file must be UTF-8 encoded.")
    try:
        template_id, amount = _resolve_billing_source(
            request, class_id, fee_template_id, custom_amount
        )
        result = _service(request).import_students_csv(
            user=user,
            class_id=class_id,
            content=content,
            filename=file.filename or "students.csv",
            enrolled_on=enrolled_on,
            fee_template_id=template_id,
            custom_amount=amount,
        )
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    except StudentImportError as exc:
        return _import_form_response(request, class_id, error=str(exc))
    return _templates(request).TemplateResponse(
        request=request,
        name="students/import_result.html",
        context={"class_id": class_id, "result": result},
    )


def _import_form_context(
    request: Request, class_id: int, class_name: str, error: str = ""
) -> dict[str, object]:
    try:
        default_template_id = _class_default_template_id(request, class_id)
    except ClassNotFound:
        default_template_id = None
    return {
        "class_id": class_id,
        "class_name": class_name,
        "error": error,
        "template_options": _template_options(request),
        "default_template_id": str(default_template_id) if default_template_id is not None else "",
        "months": [(i, MONTH_NAMES[i - 1]) for i in range(1, 13)],
    }


def _import_form_response(request: Request, class_id: int, *, error: str) -> HTMLResponse:
    try:
        class_name = _service(request).class_name(class_id)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/import.html",
        context=_import_form_context(request, class_id, class_name, error=error),
        status_code=400,
    )

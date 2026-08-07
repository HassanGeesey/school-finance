"""Student routes: add, edit, archive/restore, search, and CSV import.

Thin adapters over :class:`app.students.service.StudentService`. Viewing
(reading the class page's student list, the search page) is open to any
logged-in user; every mutation (add, edit, archive, restore, import) is
Admin-only and audited by the service layer. The import reports what was
imported and which rows were skipped.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.deps import require_admin, require_login
from ..classes.service import ClassNotFound, ClassService
from ..fees.service import period_label
from ..models import User
from ..reports.service import PAID_STATUS_LABELS, ReportService, StudentStatusRow
from .service import StudentError, StudentImportError, StudentNotFound, StudentService

router = APIRouter(include_in_schema=False)

PAID_STATUS_TONES = {
    "paid": "success",
    "partial": "warning",
    "unpaid": "error",
}


def _service(request: Request) -> StudentService:
    service = request.app.state.students
    assert isinstance(service, StudentService)
    return service


def _reports(request: Request) -> ReportService:
    service = request.app.state.reports
    assert isinstance(service, ReportService)
    return service


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
        for year, month in billed_periods
    ]
    period_values = {value for value, _ in period_options}
    selected_period = (
        period
        if period in period_values
        else (period_options[0][0] if period_options else "")
    )
    selected_status = status if status in PAID_STATUS_LABELS else ""

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
            "paid_status_labels": PAID_STATUS_LABELS,
            "paid_status_tones": PAID_STATUS_TONES,
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
        context={"student": student, "first_name": student.first_name, "last_name": student.last_name, "error": ""},
    )


@router.post("/students/{student_id}/edit", response_class=HTMLResponse)
def edit_student(
    request: Request,
    student_id: int,
    first_name: str = Form(""),
    last_name: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        student = _service(request).update_student(
            user=user, student_id=student_id, first_name=first_name, last_name=last_name
        )
    except StudentNotFound:
        raise HTTPException(status_code=404, detail="Student not found.")
    except StudentError as exc:
        return _templates(request).TemplateResponse(
            request=request,
            name="students/edit.html",
            context={
                "student": _service(request).get_student(student_id),
                "first_name": first_name,
                "last_name": last_name,
                "error": str(exc),
            },
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


@router.post("/classes/{class_id}/students", response_class=HTMLResponse)
def add_student(
    request: Request,
    class_id: int,
    first_name: str = Form(""),
    last_name: str = Form(""),
    user: User = Depends(require_admin),
) -> Response:
    try:
        _service(request).add_student(
            user=user, class_id=class_id, first_name=first_name, last_name=last_name
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
        context={"class_id": class_id, "class_name": class_name, "error": ""},
    )


@router.post("/classes/{class_id}/students/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    class_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        content = file.file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _import_form_response(request, class_id, error="The CSV file must be UTF-8 encoded.")
    try:
        result = _service(request).import_students_csv(
            user=user, class_id=class_id, content=content, filename=file.filename or "students.csv"
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


def _import_form_response(request: Request, class_id: int, *, error: str) -> HTMLResponse:
    try:
        class_name = _service(request).class_name(class_id)
    except ClassNotFound:
        raise HTTPException(status_code=404, detail="Class not found.")
    return _templates(request).TemplateResponse(
        request=request,
        name="students/import.html",
        context={"class_id": class_id, "class_name": class_name, "error": error},
        status_code=400,
    )

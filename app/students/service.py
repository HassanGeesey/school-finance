"""Students service layer.

Business rules for registering, importing, and archiving students. Routes are
thin adapters over this module — it is the single testing seam.

Rules that live here (fee-billing rework — FW-8..FW-14, FW-19/FW-20):
- A student is created inside a class (``class_id``) with a first and last
  name, an enrollment date (``enrolled_on``, default today, back-datable), and
  a billing source: a linked :class:`FeeTemplate` or a custom monthly amount.
  The billing start seeds the student's effective-dated amount schedule with a
  baseline ``StudentAmountChange`` at the enrollment month, so every owed month
  resolves an amount in force (FW-20).
- Archiving is a status transition (active -> inactive) that captures
  ``archived_on`` (the leaving month's charge stays — service-through-period-
  end, FW-14); the row, its history, and any future arrears stay. Restore is
  the reverse and clears the archive date.
- Changing a student's monthly amount is effective-dated: it carries an
  effective month (default next month, never past) and records a per-student
  amount change; a custom amount override also unlinks the template so future
  template raises stop applying (FW-19/FW-20). Linking a template re-seeds the
  amount from that month.
- A student can be searched for by name across all classes.
- CSV import: the file holds student fields only (first name, last name). The
  first row may be a header or data. Rows that are blank, missing a name, or
  duplicated within the file are skipped and reported, never silently dropped.
  Every imported student shares the form's enrollment date and billing source.
- Every mutation is recorded in the audit log with the acting user.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..classes.service import ClassNotFound
from ..db import Database
from ..fees.service import default_effective_month, period_label
from ..models import (
    Class,
    FeeTemplate,
    Student,
    StudentAmountChange,
    StudentStatus,
    User,
)
from ..money import (
    AmountInput,
    InvalidAmount,
    NonPositiveAmount,
    parse_positive_cents,
)
from ..tenants.scope import campus_for_write, in_scope, scope, scoped_campus_filter


class StudentError(Exception):
    """Rejected input or state in a student operation."""


class StudentNotFound(StudentError):
    """No student exists with the given id."""


class StudentImportError(StudentError):
    """The CSV file itself could not be imported (not row-level skips)."""


class TemplateNotFound(StudentError):
    """The fee template chosen for a student does not exist."""


@dataclass
class ImportedRow:
    """One student successfully imported from a CSV row."""

    row_number: int
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class SkippedRow:
    """One CSV row that was not imported, with the reason why."""

    row_number: int
    reason: str


@dataclass
class ImportResult:
    """The report of one CSV import: what was imported and what was skipped."""

    class_id: int
    class_name: str
    imported: list[ImportedRow] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


# CSV header cells accepted, matched case-insensitively and after trimming.
# Bare "first"/"last" are deliberately excluded so a student genuinely named
# "First Last" is not mistaken for a header.
_FIRST_NAME_HEADERS = {"first_name", "first name", "firstname"}
_LAST_NAME_HEADERS = {"last_name", "last name", "lastname", "surname"}


@dataclass
class ParsedRow:
    """One data row of a students CSV, with its physical line number."""

    line_number: int
    first_name: str
    last_name: str


def parse_students_csv(content: str) -> list[ParsedRow]:
    """Parse a students CSV into data rows with physical line numbers.

    The first non-blank row is treated as a header when its cells are
    recognizable header names; otherwise every row is a student. Blank lines are
    dropped silently; caller validation decides import vs. skip for the rest.
    """
    cleaned = content.lstrip("\ufeff")
    rows: list[ParsedRow] = []
    first_data_row_seen = False
    for line_number, raw in enumerate(csv.reader(io.StringIO(cleaned)), start=1):
        cells = [cell.strip() for cell in raw]
        if all(cell == "" for cell in cells):
            continue
        if not first_data_row_seen:
            first_data_row_seen = True
            if len(cells) >= 2 and _is_header_row(cells):
                continue
        rows.append(
            ParsedRow(
                line_number,
                cells[0] if cells else "",
                cells[1] if len(cells) > 1 else "",
            )
        )
    return rows


def _is_header_row(cells: list[str]) -> bool:
    first = cells[0].strip().lower()
    last = cells[1].strip().lower()
    return first in _FIRST_NAME_HEADERS and last in _LAST_NAME_HEADERS


class StudentService:
    """Student business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    def _get_student(self, session: Session, student_id: int) -> Student:
        student = session.get(Student, student_id)
        if student is None:
            raise StudentNotFound(f"No student with id {student_id} exists.")
        cur = scope()
        if cur is not None and not in_scope(session, cur, student.campus_id):
            raise StudentNotFound(f"No student with id {student_id} exists.")
        return student

    def _get_class(self, session: Session, class_id: int) -> Class:
        cls = session.get(Class, class_id)
        if cls is None:
            raise ClassNotFound(f"No class with id {class_id} exists.")
        cur = scope()
        if cur is not None and not in_scope(session, cur, cls.campus_id):
            raise ClassNotFound(f"No class with id {class_id} exists.")
        return cls

    @staticmethod
    def _validate_name(name: str, field_name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise StudentError(f"{field_name} is required.")
        return cleaned

    @staticmethod
    def _validate_enrolled_on(value: object) -> date:
        if isinstance(value, date):
            return value
        raw = value if isinstance(value, str) else ""
        raw = raw.strip()
        if not raw:
            return date.today()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise StudentError("Enter a valid enrollment date.") from None

    @staticmethod
    def _validate_amount(amount: AmountInput) -> int:
        try:
            return parse_positive_cents(amount)
        except InvalidAmount:
            raise StudentError("Enter a valid monthly amount.") from None
        except NonPositiveAmount:
            raise StudentError("Monthly amount must be greater than zero.") from None

    @staticmethod
    def _get_template(session: Session, template_id: int) -> FeeTemplate:
        template = session.get(FeeTemplate, template_id)
        if template is None:
            raise TemplateNotFound(f"No fee template with id {template_id} exists.")
        cur = scope()
        if cur is not None and not in_scope(session, cur, template.campus_id):
            raise TemplateNotFound(f"No fee template with id {template_id} exists.")
        return template

    @staticmethod
    def _seed_amount(
        session: Session,
        student_id: int,
        amount_cents: int,
        month: int,
        year: int,
    ) -> StudentAmountChange:
        """Write the student's amount in force for ``month``/``year``.

        The baseline of the effective-dated schedule: seeded at enrollment (and
        on every explicit amount/template change) so any owed month resolves an
        amount. An existing entry at exactly that month is updated in place, so
        the schedule never stacks two entries on one month.
        """
        row = (
            session.query(StudentAmountChange)
            .filter(
                StudentAmountChange.student_id == student_id,
                StudentAmountChange.month == month,
                StudentAmountChange.year == year,
            )
            .one_or_none()
        )
        if row is None:
            row = StudentAmountChange(
                student_id=student_id,
                campus_id=campus_for_write(scope()),
                amount_cents=amount_cents,
                month=month,
                year=year,
            )
            session.add(row)
        else:
            row.amount_cents = amount_cents
        return row

    def add_student(
        self,
        *,
        user: User | None,
        class_id: int,
        first_name: str,
        last_name: str,
        enrolled_on: object | None = None,
        fee_template_id: int | None = None,
        custom_amount: AmountInput | None = None,
    ) -> Student:
        """Register one student inside a class with their billing start.

        Either a linked template or a custom monthly amount is required; the
        chosen amount is seeded as the amount in force from the enrollment
        month. The class's default template pre-fills the form but is not
        applied automatically here.
        """
        first_name = self._validate_name(first_name, "First name")
        last_name = self._validate_name(last_name, "Last name")
        enrolled_on = self._validate_enrolled_on(enrolled_on)
        if fee_template_id is None and custom_amount is None:
            raise StudentError("Choose a fee template or enter a monthly amount.")

        with self._session() as session:
            cur = scope()
            cls = self._get_class(session, class_id)
            student = Student(
                class_id=class_id,
                campus_id=campus_for_write(cur),
                first_name=first_name,
                last_name=last_name,
                status=StudentStatus.ACTIVE,
                enrolled_on=enrolled_on,
                fee_template_id=fee_template_id,
            )
            session.add(student)
            session.flush()
            if fee_template_id is not None:
                template = self._get_template(session, fee_template_id)
                amount_cents = template.amount_cents
            else:
                assert custom_amount is not None
                amount_cents = self._validate_amount(custom_amount)
            self._seed_amount(
                session,
                student.id,
                amount_cents,
                enrolled_on.month,
                enrolled_on.year,
            )
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_ADD,
            summary=f"Added student {student.full_name} to class {cls.name}",
        )
        return student

    def update_student(
        self,
        *,
        user: User | None,
        student_id: int,
        first_name: str,
        last_name: str,
        enrolled_on: object | None = None,
    ) -> Student:
        """Change a student's names and/or enrollment date.

        ``enrolled_on`` is only rewritten when the form actually changes it.
        Because the amount schedule is effective-dated, moving the enrollment
        month does not rewrite past amounts — an owed month always resolves the
        amount in force for that month. Unchanged fields produce no audit noise.
        """
        first_name = self._validate_name(first_name, "First name")
        last_name = self._validate_name(last_name, "Last name")
        enrolled_on = self._validate_enrolled_on(enrolled_on)

        changed_enrollment = False
        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.first_name == first_name and student.last_name == last_name:
                return student
            old = student.full_name
            student.first_name = first_name
            student.last_name = last_name
            new = student.full_name
            if enrolled_on != student.enrolled_on:
                student.enrolled_on = enrolled_on
                changed_enrollment = True
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_UPDATE,
            summary=(
                f"Updated student {old} to {new}"
                + (
                    f" (enrollment date changed to {student.enrolled_on.isoformat()})"
                    if changed_enrollment
                    else ""
                )
            ),
        )
        return student

    def archive_student(
        self,
        *,
        user: User | None,
        student_id: int,
        archived_on: object | None = None,
    ) -> Student:
        """Mark a student inactive, capturing their leaving date.

        The month of ``archived_on`` is still owed (service-through-period-end,
        FW-14); owed months stop after it. History and arrears are kept;
        nothing is deleted.
        """
        if isinstance(archived_on, date):
            leaving = archived_on
        else:
            raw = archived_on if isinstance(archived_on, str) else ""
            raw = raw.strip()
            if not raw:
                leaving = date.today()
            else:
                try:
                    leaving = date.fromisoformat(raw)
                except ValueError:
                    raise StudentError("Enter a valid leaving date.") from None
        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.status == StudentStatus.INACTIVE:
                return student
            student.status = StudentStatus.INACTIVE
            student.archived_on = leaving
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_ARCHIVE,
            summary=(
                f"Archived student {student.full_name} "
                f"(owed through {period_label(leaving.month, leaving.year)})"
            ),
        )
        return student

    def restore_student(self, *, user: User | None, student_id: int) -> Student:
        """Mark an archived student active again; the archive date is cleared."""
        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.status == StudentStatus.ACTIVE:
                return student
            student.status = StudentStatus.ACTIVE
            student.archived_on = None
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_RESTORE,
            summary=f"Restored student {student.full_name}",
        )
        return student

    def change_amount(
        self,
        *,
        user: User | None,
        student_id: int,
        amount: AmountInput,
        month: int | None = None,
        year: int | None = None,
    ) -> Student:
        """Set a student's own monthly amount, effective from a month.

        Defaults to next month (FW-20 — never past). Records a per-student
        amount change and unlinks the template, so this student no longer
        follows template raises (FW-19).
        """
        amount_cents = self._validate_amount(amount)
        if month is None or year is None:
            month, year = default_effective_month()
        with self._session() as session:
            student = self._get_student(session, student_id)
            student.fee_template_id = None
            self._seed_amount(session, student.id, amount_cents, month, year)
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_AMOUNT_CHANGE,
            summary=(
                f"Changed {student.full_name}'s monthly amount to "
                f"${amount_cents / 100:,.2f} effective {period_label(month, year)}"
            ),
        )
        return student

    def set_template(
        self,
        *,
        user: User | None,
        student_id: int,
        fee_template_id: int,
        month: int | None = None,
        year: int | None = None,
    ) -> Student:
        """Link a student to a fee template from an effective month.

        Defaults to next month; the template's current amount is seeded at that
        month so the student's amount in force tracks the template from then on.
        """
        if month is None or year is None:
            month, year = default_effective_month()
        with self._session() as session:
            student = self._get_student(session, student_id)
            template = self._get_template(session, fee_template_id)
            student.fee_template_id = template.id
            self._seed_amount(session, student.id, template.amount_cents, month, year)
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_TEMPLATE,
            summary=(
                f"Linked {student.full_name} to fee template {template.name} "
                f"effective {period_label(month, year)}"
            ),
        )
        return student

    def get_student(self, student_id: int) -> Student:
        with self._session() as session:
            student = (
                session.query(Student)
                .options(joinedload(Student.school_class))
                .filter(Student.id == student_id)
                .one_or_none()
            )
            if student is None:
                raise StudentNotFound(f"No student with id {student_id} exists.")
            cur = scope()
            if cur is not None and not in_scope(session, cur, student.campus_id):
                raise StudentNotFound(f"No student with id {student_id} exists.")
        return student

    def class_name(self, class_id: int) -> str:
        with self._session() as session:
            return self._get_class(session, class_id).name

    def list_students(self, class_id: int, status: str | None = None) -> list[Student]:
        """Students of one class, sorted by name, optionally filtered by status."""
        with self._session() as session:
            self._get_class(session, class_id)
            cur = scope()
            query = session.query(Student).filter(Student.class_id == class_id)
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Student.campus_id))
            if status:
                query = query.filter(Student.status == status)
            return (
                query.order_by(Student.last_name, Student.first_name, Student.id).all()
            )

    def search_students(self, query: str, class_id: int | None = None) -> list[Student]:
        """Find students by name, optionally narrowed to one class.

        Matching is case-insensitive substring matching; results include archived
        students (history and arrears stay). The class is eagerly loaded so
        results can be rendered outside the session. An unknown ``class_id``
        raises :class:`ClassNotFound`, matching :meth:`list_students`.
        """
        term = (query or "").strip()
        with self._session() as session:
            cur = scope()
            q = session.query(Student).options(joinedload(Student.school_class))
            if cur is not None:
                q = q.filter(scoped_campus_filter(session, cur, Student.campus_id))
            if class_id is not None:
                self._get_class(session, class_id)
                q = q.filter(Student.class_id == class_id)
            if term:
                like = f"%{term}%"
                q = q.filter(
                    Student.first_name.ilike(like)
                    | Student.last_name.ilike(like)
                    | (Student.first_name + " " + Student.last_name).ilike(like)
                )
            return q.order_by(Student.last_name, Student.first_name, Student.id).all()

    def import_students_csv(
        self,
        *,
        user: User | None,
        class_id: int,
        content: str,
        filename: str = "students.csv",
        enrolled_on: object | None = None,
        fee_template_id: int | None = None,
        custom_amount: AmountInput | None = None,
    ) -> ImportResult:
        """Import students from a CSV and report what was imported and skipped.

        Each data row is ``(first_name, last_name)``. A leading header row is
        recognised when its cells are known header names. Rows that are blank,
        missing a name, or duplicated within the file are skipped with a reason;
        everything else is imported in one transaction with the form's
        enrollment date and billing source (template or custom amount) applied
        to every row. The report's row numbers are the physical CSV line
        numbers, and the audit entry records how many rows were skipped.
        """
        rows = parse_students_csv(content)
        if not rows:
            raise StudentImportError("No student rows found in the file.")
        if fee_template_id is None and custom_amount is None:
            raise StudentImportError("Choose a fee template or enter a monthly amount.")
        enrolled_on = self._validate_enrolled_on(enrolled_on)
        if fee_template_id is None:
            assert custom_amount is not None
            amount_cents = self._validate_amount(custom_amount)
        else:
            amount_cents = None

        imported: list[ImportedRow] = []
        skipped: list[SkippedRow] = []
        seen: set[tuple[str, str]] = set()
        with self._session() as session:
            cur = scope()
            cls = self._get_class(session, class_id)
            template = (
                self._get_template(session, fee_template_id)
                if fee_template_id is not None
                else None
            )
            for parsed in rows:
                first_name, last_name = parsed.first_name, parsed.last_name
                if not first_name:
                    skipped.append(SkippedRow(parsed.line_number, "Missing first name."))
                    continue
                if not last_name:
                    skipped.append(SkippedRow(parsed.line_number, "Missing last name."))
                    continue
                key = (first_name.lower(), last_name.lower())
                if key in seen:
                    skipped.append(SkippedRow(parsed.line_number, "duplicate within the file."))
                    continue
                seen.add(key)
                student = Student(
                    class_id=class_id,
                    campus_id=campus_for_write(cur),
                    first_name=first_name,
                    last_name=last_name,
                    status=StudentStatus.ACTIVE,
                    enrolled_on=enrolled_on,
                    fee_template_id=template.id if template is not None else None,
                )
                session.add(student)
                session.flush()
                seed_cents = template.amount_cents if template is not None else amount_cents
                assert seed_cents is not None  # custom amount verified above when no template
                self._seed_amount(
                    session,
                    student.id,
                    seed_cents,
                    enrolled_on.month,
                    enrolled_on.year,
                )
                imported.append(ImportedRow(parsed.line_number, first_name, last_name))
            session.commit()
        summary = f"Imported {len(imported)} student(s) into class {cls.name} from {filename}"
        if skipped:
            summary += f" ({len(skipped)} row(s) skipped)"
        self._log(
            user=user,
            action=AuditActions.STUDENT_IMPORT,
            summary=summary,
        )
        return ImportResult(
            class_id=class_id,
            class_name=cls.name,
            imported=imported,
            skipped=skipped,
        )

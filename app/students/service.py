"""Students service layer.

Business rules for registering, importing, and archiving students. Routes are
thin adapters over this module — it is the single testing seam.

Rules that live here:
- A student is created inside a class (``class_id``) with a first and last name;
  names are required and trimmed. Imported students are plain class members too
  and inherit nothing at this layer — they become part of the class, so fee
  generation later bills them exactly like manually added students.
- Archiving is a status transition (active -> inactive), never a delete: the
  row, its history, and any future arrears stay. Restore is the reverse.
- A student can be searched for by name across all classes.
- CSV import: the file holds student fields only (first name, last name). The
  first row may be a header or data. Rows that are blank, missing a name, or
  duplicated within the file are skipped and reported, never silently dropped.
- Every mutation is recorded in the audit log with the acting user.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..classes.service import ClassNotFound
from ..db import Database
from ..models import Class, Student, StudentStatus, User


class StudentError(Exception):
    """Rejected input or state in a student operation."""


class StudentNotFound(StudentError):
    """No student exists with the given id."""


class StudentImportError(StudentError):
    """The CSV file itself could not be imported (not row-level skips)."""


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
        return student

    def _get_class(self, session: Session, class_id: int) -> Class:
        cls = session.get(Class, class_id)
        if cls is None:
            raise ClassNotFound(f"No class with id {class_id} exists.")
        return cls

    @staticmethod
    def _validate_name(name: str, field_name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise StudentError(f"{field_name} is required.")
        return cleaned

    def add_student(
        self,
        *,
        user: User | None,
        class_id: int,
        first_name: str,
        last_name: str,
    ) -> Student:
        """Register one student inside a class."""
        first_name = self._validate_name(first_name, "First name")
        last_name = self._validate_name(last_name, "Last name")

        with self._session() as session:
            cls = self._get_class(session, class_id)
            student = Student(
                class_id=class_id,
                first_name=first_name,
                last_name=last_name,
                status=StudentStatus.ACTIVE,
            )
            session.add(student)
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
    ) -> Student:
        """Change a student's names. Unchanged fields produce no audit noise."""
        first_name = self._validate_name(first_name, "First name")
        last_name = self._validate_name(last_name, "Last name")

        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.first_name == first_name and student.last_name == last_name:
                return student
            old = student.full_name
            student.first_name = first_name
            student.last_name = last_name
            new = student.full_name
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_UPDATE,
            summary=f"Updated student {old} to {new}",
        )
        return student

    def archive_student(self, *, user: User | None, student_id: int) -> Student:
        """Mark a student inactive. History and arrears are kept; nothing is deleted."""
        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.status == StudentStatus.INACTIVE:
                return student
            student.status = StudentStatus.INACTIVE
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_ARCHIVE,
            summary=f"Archived student {student.full_name}",
        )
        return student

    def restore_student(self, *, user: User | None, student_id: int) -> Student:
        """Mark an archived student active again."""
        with self._session() as session:
            student = self._get_student(session, student_id)
            if student.status == StudentStatus.ACTIVE:
                return student
            student.status = StudentStatus.ACTIVE
            session.commit()
            session.refresh(student)
        self._log(
            user=user,
            action=AuditActions.STUDENT_RESTORE,
            summary=f"Restored student {student.full_name}",
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
        return student

    def class_name(self, class_id: int) -> str:
        with self._session() as session:
            return self._get_class(session, class_id).name

    def list_students(self, class_id: int, status: str | None = None) -> list[Student]:
        """Students of one class, sorted by name, optionally filtered by status."""
        with self._session() as session:
            self._get_class(session, class_id)
            query = session.query(Student).filter(Student.class_id == class_id)
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
            q = session.query(Student).options(joinedload(Student.school_class))
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
    ) -> ImportResult:
        """Import students from a CSV and report what was imported and skipped.

        Each data row is ``(first_name, last_name)``. A leading header row is
        recognised when its cells are known header names. Rows that are blank,
        missing a name, or duplicated within the file are skipped with a reason;
        everything else is imported in one transaction. The report's row numbers
        are the physical CSV line numbers, and the audit entry records how many
        rows were skipped.
        """
        rows = parse_students_csv(content)
        if not rows:
            raise StudentImportError("No student rows found in the file.")

        imported: list[ImportedRow] = []
        skipped: list[SkippedRow] = []
        seen: set[tuple[str, str]] = set()
        with self._session() as session:
            cls = self._get_class(session, class_id)
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
                session.add(
                    Student(
                        class_id=class_id,
                        first_name=first_name,
                        last_name=last_name,
                        status=StudentStatus.ACTIVE,
                    )
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

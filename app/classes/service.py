"""Classes service layer: grouping students under a default fee template.

Business rules for the Admin's configuration surface: classes (create/rename/
status) and each class's default fee template (FW-7). Routes are thin adapters
over this module — it is the single testing seam.

Rules that live here:
- A class name is required; status is one of active/completed/inactive.
- Completed/Inactive classes keep their records but stop appearing as billing
  targets later; they can be reopened here.
- A class carries an optional default :class:`FeeTemplate`. The template's
  monthly amount is what each of the class's students is expected to pay
  (a student may still be linked to another template or hold a custom amount).
  Setting/clearing the default is a status-of-record change, audited with the
  acting user. Templates are Admin-managed (Q24).
- Every change is recorded in the audit log with the acting user.
- There are no hard deletes: a class is never destroyed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import Class, ClassStatus, FeeTemplate, Student, User
from ..money import Money

CLASS_STATUS_LABELS = {
    ClassStatus.ACTIVE: "Active",
    ClassStatus.COMPLETED: "Completed",
    ClassStatus.INACTIVE: "Inactive",
}

VALID_STATUSES = set(CLASS_STATUS_LABELS)


class ClassError(Exception):
    """Rejected input or state in a class operation."""


class ClassNotFound(ClassError):
    """No class exists with the given id."""


@dataclass
class ClassSummary:
    """One class with its student count and the monthly fee per student.

    ``monthly_total_cents`` is the default template's amount (0 when the class
    has no default yet). ``arrears_cents`` is filled in by the route layer from
    the arrears report (rework tickets 06/08) — the service itself reports 0.
    """

    cls: Class
    student_count: int
    monthly_total_cents: Money
    arrears_cents: Money


class ClassService:
    """Class business rules. Each public method is one unit of work on its own session."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    def _get_class(self, session: Session, class_id: int) -> Class:
        cls = session.get(Class, class_id)
        if cls is None:
            raise ClassNotFound(f"No class with id {class_id} exists.")
        return cls

    def _get_class_with_template(self, session: Session, class_id: int) -> Class:
        cls = (
            session.query(Class)
            .options(joinedload(Class.default_template))
            .filter(Class.id == class_id)
            .one_or_none()
        )
        if cls is None:
            raise ClassNotFound(f"No class with id {class_id} exists.")
        return cls

    @staticmethod
    def _template_option(session: Session, template_id: int) -> FeeTemplate:
        """Resolve a posted template id to a live template, or reject it."""
        template = session.get(FeeTemplate, template_id)
        if template is None or template.archived:
            raise ClassError("Choose a valid fee template.")
        return template

    @staticmethod
    def _validate_name(name: str, field: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ClassError(f"{field} is required.")
        return cleaned

    @staticmethod
    def _validate_status(status: str) -> str:
        if status not in VALID_STATUSES:
            raise ClassError("Invalid class status.")
        return status

    def create_class(
        self,
        *,
        user: User | None,
        name: str,
        status: str = ClassStatus.ACTIVE,
        default_template_id: int | None = None,
    ) -> Class:
        """Create a class. Names are required; status defaults to Active.

        ``default_template_id`` optionally links the class's default fee
        template (the monthly amount its students are expected to pay).
        """
        name = self._validate_name(name, "Class name")
        status = self._validate_status(status)

        with self._session() as session:
            template = (
                self._template_option(session, default_template_id)
                if default_template_id is not None
                else None
            )
            cls = Class(
                name=name,
                status=status,
                default_template_id=template.id if template is not None else None,
            )
            session.add(cls)
            session.commit()
            session.refresh(cls)
        self._log(user=user, action=AuditActions.CLASS_CREATE, summary=f"Created class {cls.name}")
        return cls

    def update_class(
        self,
        *,
        user: User | None,
        class_id: int,
        name: str,
        status: str,
    ) -> Class:
        """Rename and/or change the status of a class in one unit of work.

        Each field that actually changes is audited separately; unchanged fields
        produce no noise. Reopening a Completed/Inactive class is just selecting
        ``active`` again.
        """
        name = self._validate_name(name, "Class name")
        status = self._validate_status(status)

        renamed: tuple[str, str] | None = None
        status_change: str | None = None
        with self._session() as session:
            cls = self._get_class(session, class_id)
            if cls.name != name:
                renamed = (cls.name, name)
                cls.name = name
            if cls.status != status:
                status_change = status
                cls.status = status
            session.commit()
            session.refresh(cls)
        if renamed is not None:
            self._log(
                user=user,
                action=AuditActions.CLASS_RENAME,
                summary=f"Renamed class {renamed[0]} to {renamed[1]}",
            )
        if status_change is not None:
            self._log(
                user=user,
                action=AuditActions.CLASS_STATUS,
                summary=f"Set class {cls.name} status to {CLASS_STATUS_LABELS[status_change]}",
            )
        return cls

    def set_default_template(
        self,
        *,
        user: User | None,
        class_id: int,
        default_template_id: int | None,
    ) -> Class:
        """Point a class at a default fee template, or clear it (``None``).

        Only live (non-archived) templates can be chosen. Unchanged selections
        produce no audit noise.
        """
        with self._session() as session:
            cls = self._get_class(session, class_id)
            template = (
                self._template_option(session, default_template_id)
                if default_template_id is not None
                else None
            )
            new_id = template.id if template is not None else None
            if cls.default_template_id == new_id:
                return cls
            old_name = cls.default_template.name if cls.default_template is not None else None
            new_name = template.name if template is not None else None
            cls.default_template_id = new_id
            session.commit()
            session.refresh(cls)
        if new_name is None:
            summary = f"Cleared class {cls.name} default template"
            if old_name is not None:
                summary += f" ({old_name})"
        else:
            summary = f"Set class {cls.name} default template to {new_name}"
        self._log(user=user, action=AuditActions.CLASS_DEFAULT_TEMPLATE, summary=summary)
        return cls

    def get_class(self, class_id: int) -> Class:
        with self._session() as session:
            return self._get_class(session, class_id)

    def class_summary(self, class_id: int) -> ClassSummary:
        """One class with its student count and the default monthly fee."""
        with self._session() as session:
            cls = self._get_class_with_template(session, class_id)
            student_count = (
                session.query(func.count(Student.id)).filter(Student.class_id == class_id).scalar()
                or 0
            )
            return self._to_summary(cls, int(student_count))

    def list_class_summaries(self) -> list[ClassSummary]:
        """Every class with its summary, oldest first."""
        with self._session() as session:
            classes = (
                session.query(Class)
                .options(joinedload(Class.default_template))
                .order_by(Class.created_at, Class.id)
                .all()
            )
            counts: dict[int, int] = {
                class_id: int(count)
                for class_id, count in (
                    session.query(Student.class_id, func.count(Student.id))
                    .group_by(Student.class_id)
                    .all()
                )
            }
            return [self._to_summary(cls, counts.get(cls.id, 0)) for cls in classes]

    @staticmethod
    def _to_summary(cls: Class, student_count: int) -> ClassSummary:
        amount = cls.default_template.amount_cents if cls.default_template is not None else 0
        return ClassSummary(
            cls=cls,
            student_count=student_count,
            monthly_total_cents=amount,
            arrears_cents=0,
        )

    def student_counts(self) -> dict[int, int]:
        """How many students belong to each class id."""
        with self._session() as session:
            rows = (
                session.query(Student.class_id, func.count(Student.id))
                .group_by(Student.class_id)
                .all()
            )
        return {class_id: int(count) for class_id, count in rows}

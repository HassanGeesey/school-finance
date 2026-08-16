"""Fee template service layer: the Admin's fee plans.

The fee-billing rework replaced charge rows with templates: a :class:`FeeTemplate`
is a named monthly amount a class defaults to and a student can be linked to
(``CONTEXT.md`` — "Fee Template"). This module is the Admin's configuration
surface for those templates. Routes are thin adapters over it — it is the single
testing seam.

Rules that live here:
- A template name is required; the amount is positive integer cents
  (``app.money``), never floats.
- An **amount change is effective-dated** (FW-20): it carries an effective month
  (default: next month) that may not be before the current month, so past months
  are frozen. The change propagates to every student linked to the template,
  writing one per-student amount-change entry at the effective month so a month's
  expected amount can be resolved without rewriting history.
- Renaming a template changes its name for every linked student (the linkage is
  by id, not by name); it never touches amounts or history.
- Archiving is a status transition (no hard deletes): an archived template stops
  appearing in pickers but keeps its linkage and history; restore is the reverse.
- Every change is recorded in the audit log with the acting user.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import (
    ClosedMonth,
    FeeTemplate,
    Student,
    StudentAmountChange,
    User,
    Waiver,
)
from ..tenants.scope import (
    campus_for_write,
    in_scope,
    require_scope,
    scoped_campus_filter,
)
from ..money import (
    AmountInput,
    InvalidAmount,
    NonPositiveAmount,
    format_cents,
    parse_positive_cents,
)

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

MIN_YEAR = 2000
MAX_YEAR = 2100


class TemplateError(Exception):
    """Rejected input or state in a fee-template operation."""


class TemplateNotFound(TemplateError):
    """No fee template exists with the given id."""


class InvalidPeriod(TemplateError):
    """The effective month/year falls outside the supported range, or is past."""


def period_label(month: int, year: int) -> str:
    """Human label for a month+year, e.g. ``April 2026``."""
    return f"{MONTH_NAMES[month - 1]} {year}"


def default_effective_month() -> tuple[int, int]:
    """The month/year an amount change defaults to: the next calendar month."""
    today = date.today()
    if today.month == 12:
        return 1, today.year + 1
    return today.month + 1, today.year


class TemplateService:
    """Fee-template business rules. Each public method is one unit of work."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _get_template(session: Session, template_id: int) -> FeeTemplate:
        template = session.get(FeeTemplate, template_id)
        if template is None:
            raise TemplateNotFound(f"No fee template with id {template_id} exists.")
        cur = require_scope()
        if cur is not None and not in_scope(session, cur, template.campus_id):
            raise TemplateNotFound(f"No fee template with id {template_id} exists.")
        return template

    @staticmethod
    def _validate_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise TemplateError("A template name is required.")
        return cleaned

    @staticmethod
    def _validate_amount(amount: AmountInput) -> int:
        try:
            return parse_positive_cents(amount)
        except InvalidAmount:
            raise TemplateError("Enter a valid amount.") from None
        except NonPositiveAmount:
            raise TemplateError("Amount must be greater than zero.") from None

    @classmethod
    def _validate_effective_month(
        cls, month: int | None, year: int | None
    ) -> tuple[int, int]:
        """Coerce and validate the month an amount change takes effect.

        ``None``/``None`` means "next month" (the default). Both must be given
        together, the month must be 1-12 and the year within range, and the
        month may not be before the current month — past months are frozen
        (FW-20).
        """
        if month is None and year is None:
            return default_effective_month()
        if month is None or year is None:
            raise InvalidPeriod("Choose both the month and the year the change takes effect.")
        if not isinstance(month, int) or not 1 <= month <= 12:
            raise InvalidPeriod("Choose a month between 1 and 12.")
        if not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
            raise InvalidPeriod(f"Choose a year between {MIN_YEAR} and {MAX_YEAR}.")
        today = date.today()
        if (year, month) < (today.year, today.month):
            raise InvalidPeriod(
                "The effective month cannot be in the past — past months are already set."
            )
        return month, year

    def create_template(
        self,
        *,
        user: User | None,
        name: str,
        amount: AmountInput,
    ) -> FeeTemplate:
        """Create a fee template with an initial monthly amount."""
        name = self._validate_name(name)
        amount_cents = self._validate_amount(amount)

        with self._session() as session:
            template = FeeTemplate(
                name=name,
                amount_cents=amount_cents,
                campus_id=campus_for_write(require_scope()),
            )
            session.add(template)
            session.commit()
            session.refresh(template)
        self._log(
            user=user,
            action=AuditActions.TEMPLATE_CREATE,
            summary=(
                f"Created fee template {template.name} "
                f"({format_cents(template.amount_cents)}/month)"
            ),
        )
        return template

    def update_template(
        self,
        *,
        user: User | None,
        template_id: int,
        name: str,
        amount: AmountInput,
        month: int | None = None,
        year: int | None = None,
    ) -> FeeTemplate:
        """Rename and/or change the amount of a template in one unit of work.

        A name change is a simple rename. An amount change is effective-dated:
        it needs an effective month (default next month, never past) and
        propagates to every linked student from that month. Each field that
        actually changes is audited separately; unchanged fields produce no
        noise.
        """
        name = self._validate_name(name)
        amount_cents = self._validate_amount(amount)

        renamed: tuple[str, str] | None = None
        changed_month: tuple[int, int] | None = None
        propagated = 0
        with self._session() as session:
            template = self._get_template(session, template_id)
            if template.name != name:
                renamed = (template.name, name)
                template.name = name
            if template.amount_cents != amount_cents:
                changed_month = self._validate_effective_month(month, year)
                template.amount_cents = amount_cents
                propagated = self._propagate(
                    session,
                    template_id=template.id,
                    amount_cents=amount_cents,
                    month=changed_month[0],
                    year=changed_month[1],
                )
            session.commit()
            session.refresh(template)

        if renamed is not None:
            self._log(
                user=user,
                action=AuditActions.TEMPLATE_RENAME,
                summary=f"Renamed fee template {renamed[0]} to {renamed[1]}",
            )
        if changed_month is not None:
            summary = (
                f"Changed fee template {template.name} to "
                f"{format_cents(amount_cents)}/month effective "
                f"{period_label(*changed_month)}"
            )
            if propagated:
                summary += f" ({propagated} linked student(s) updated)"
            self._log(
                user=user,
                action=AuditActions.TEMPLATE_AMOUNT_CHANGE,
                summary=summary,
            )
        return template

    @staticmethod
    def _propagate(
        session: Session,
        *,
        template_id: int,
        amount_cents: int,
        month: int,
        year: int,
    ) -> int:
        """Write one effective-dated entry per linked student (FW-19/FW-20).

        Each student linked to the template gets a ``StudentAmountChange`` at
        ``month``/``year`` set to the new amount. A student who already has an
        entry at exactly that month is updated in place, so a template never
        stacks two entries on the same month. Returns how many linked students
        were touched (0 when no student is linked yet).

        Propagation stays within the acting Campus: linked students from another
        Campus are never touched, even when the linkage row exists (a foreign
        link is normally refused at creation, but a corrupt row must not leak
        amount changes across Campuses).
        """
        cur = require_scope()
        query = session.query(Student).filter(Student.fee_template_id == template_id)
        if cur is not None:
            query = query.filter(
                scoped_campus_filter(session, cur, Student.campus_id)
            )
        students = query.all()
        if not students:
            return 0
        existing = {
            (row.student_id, row.month, row.year): row
            for row in session.query(StudentAmountChange)
            .filter(
                StudentAmountChange.student_id.in_([student.id for student in students]),
                StudentAmountChange.month == month,
                StudentAmountChange.year == year,
            )
            .all()
        }
        campus_id = campus_for_write(cur)
        for student in students:
            row = existing.get((student.id, month, year))
            if row is None:
                session.add(
                    StudentAmountChange(
                        student_id=student.id,
                        amount_cents=amount_cents,
                        month=month,
                        year=year,
                        campus_id=campus_id,
                    )
                )
            else:
                row.amount_cents = amount_cents
                if campus_id is not None:
                    row.campus_id = campus_id
        return len(students)

    def archive_template(self, *, user: User | None, template_id: int) -> FeeTemplate:
        """Archive a template: it stops appearing in pickers but keeps its history."""
        with self._session() as session:
            template = self._get_template(session, template_id)
            if template.archived:
                return template
            template.archived = True
            session.commit()
            session.refresh(template)
        self._log(
            user=user,
            action=AuditActions.TEMPLATE_ARCHIVE,
            summary=f"Archived fee template {template.name}",
        )
        return template

    def restore_template(self, *, user: User | None, template_id: int) -> FeeTemplate:
        """Restore an archived template so it appears in pickers again."""
        with self._session() as session:
            template = self._get_template(session, template_id)
            if not template.archived:
                return template
            template.archived = False
            session.commit()
            session.refresh(template)
        self._log(
            user=user,
            action=AuditActions.TEMPLATE_RESTORE,
            summary=f"Restored fee template {template.name}",
        )
        return template

    def list_templates(self) -> list[FeeTemplate]:
        """Every template visible to the acting Campus, active ones first, then
        archived — both by name."""
        with self._session() as session:
            query = session.query(FeeTemplate)
            cur = require_scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, FeeTemplate.campus_id)
                )
            return (
                query.order_by(FeeTemplate.archived, FeeTemplate.name, FeeTemplate.id)
                .all()
            )

    def list_active_templates(self) -> list[FeeTemplate]:
        """Only non-archived templates, for the class/student pickers."""
        with self._session() as session:
            query = session.query(FeeTemplate).filter(FeeTemplate.archived.is_(False))
            cur = require_scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, FeeTemplate.campus_id)
                )
            return query.order_by(FeeTemplate.name, FeeTemplate.id).all()

    def get_template(self, template_id: int) -> FeeTemplate:
        with self._session() as session:
            return self._get_template(session, template_id)

    def linked_student_counts(self) -> dict[int, int]:
        """How many students are currently linked to each visible template id (FW-19)."""
        with self._session() as session:
            query = session.query(Student.fee_template_id, func.count(Student.id)).filter(
                Student.fee_template_id.isnot(None)
            )
            cur = require_scope()
            if cur is not None:
                query = query.filter(scoped_campus_filter(session, cur, Student.campus_id))
            rows = query.group_by(Student.fee_template_id).all()
        return {template_id: int(count) for template_id, count in rows}


class WaiverError(Exception):
    """Rejected input or state in a waiver operation."""


class WaiverService:
    """Per-(student, month) charge forgiveness (FW-10/FW-11/FW-13).

    A waiver reduces a month's expected amount by a given amount; multiple
    waivers stack on the same month and the expected never goes below zero.
    A reason/label is required, and creation is audited with the acting user
    (who and why). Both Admin and Finance officer may waive.
    """

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _validate_label(label: str) -> str:
        cleaned = (label or "").strip()
        if not cleaned:
            raise WaiverError("A reason is required.")
        return cleaned

    @staticmethod
    def _validate_amount(amount: AmountInput) -> int:
        try:
            return parse_positive_cents(amount)
        except InvalidAmount:
            raise WaiverError("Enter a valid amount.") from None
        except NonPositiveAmount:
            raise WaiverError("Amount must be greater than zero.") from None

    @staticmethod
    def _validate_period(month: int | None, year: int | None) -> tuple[int, int]:
        if not isinstance(month, int) or not 1 <= month <= 12:
            raise WaiverError("Choose a month between 1 and 12.")
        if not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
            raise WaiverError(f"Choose a year between {MIN_YEAR} and {MAX_YEAR}.")
        return month, year

    def add_waiver(
        self,
        *,
        user: User | None,
        student_id: int,
        month: int | None,
        year: int | None,
        amount: AmountInput,
        label: str,
    ) -> Waiver:
        """Apply one waiver to a (student, month)."""
        month, year = self._validate_period(month, year)
        amount_cents = self._validate_amount(amount)
        label = self._validate_label(label)

        with self._session() as session:
            student = session.get(Student, student_id)
            if student is None:
                raise WaiverError("Choose a student.")
            cur = require_scope()
            if cur is not None and not in_scope(session, cur, student.campus_id):
                raise WaiverError("Choose a student.")
            waiver = Waiver(
                student_id=student_id,
                month=month,
                year=year,
                amount_cents=amount_cents,
                label=label,
                campus_id=campus_for_write(cur),
                created_by=user.id if user is not None else None,
            )
            session.add(waiver)
            session.commit()
            session.refresh(waiver)
        self._log(
            user=user,
            action=AuditActions.WAIVER_ADD,
            summary=(
                f"Waived {format_cents(amount_cents)} for {student.full_name} "
                f"({period_label(month, year)}): {label}"
            ),
        )
        return waiver


class ClosedMonthError(Exception):
    """Rejected input or state in a closed-month operation."""


class DuplicateClosedMonth(ClosedMonthError):
    """The month is already on the closed list."""


class ClosedMonthService:
    """The school-wide closed-month list (FW-17).

    A closed month is excluded from every student's owed months — it carries no
    expected amount and never appears as unpaid. Maintained by the Admin; add
    and remove are audited.
    """

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _validate_period(month: int | None, year: int | None) -> tuple[int, int]:
        if not isinstance(month, int) or not 1 <= month <= 12:
            raise ClosedMonthError("Choose a month between 1 and 12.")
        if not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
            raise ClosedMonthError(f"Choose a year between {MIN_YEAR} and {MAX_YEAR}.")
        return month, year

    def add_closed_month(
        self, *, user: User | None, month: int | None, year: int | None
    ) -> ClosedMonth:
        month, year = self._validate_period(month, year)
        with self._session() as session:
            cur = require_scope()
            query = session.query(ClosedMonth).filter(
                ClosedMonth.month == month, ClosedMonth.year == year
            )
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, ClosedMonth.campus_id)
                )
            if query.one_or_none() is not None:
                raise DuplicateClosedMonth(
                    f"{period_label(month, year)} is already closed."
                )
            closed = ClosedMonth(
                month=month, year=year, campus_id=campus_for_write(cur)
            )
            session.add(closed)
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateClosedMonth(
                    f"{period_label(month, year)} is already closed."
                ) from None
            session.refresh(closed)
        self._log(
            user=user,
            action=AuditActions.CLOSED_MONTH_ADD,
            summary=f"Closed {period_label(month, year)} (no fees due)",
        )
        return closed

    def remove_closed_month(
        self, *, user: User | None, month: int | None, year: int | None
    ) -> None:
        month, year = self._validate_period(month, year)
        with self._session() as session:
            query = session.query(ClosedMonth).filter(
                ClosedMonth.month == month, ClosedMonth.year == year
            )
            cur = require_scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, ClosedMonth.campus_id)
                )
            closed = query.one_or_none()
            if closed is None:
                raise ClosedMonthError(
                    f"{period_label(month, year)} is not on the closed list."
                )
            session.delete(closed)
            session.commit()
        self._log(
            user=user,
            action=AuditActions.CLOSED_MONTH_REMOVE,
            summary=f"Reopened {period_label(month, year)} (fees due again)",
        )

    def list_closed_months(self) -> list[ClosedMonth]:
        """Every closed month visible to the acting Campus, newest first."""
        with self._session() as session:
            query = session.query(ClosedMonth)
            cur = require_scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, ClosedMonth.campus_id)
                )
            return (
                query.order_by(
                    ClosedMonth.year.desc(), ClosedMonth.month.desc(), ClosedMonth.id
                )
                .all()
            )

    def closed_month_set(self) -> set[tuple[int, int]]:
        """The closed months visible to the acting Campus as a lookup set of
        ``(month, year)`` pairs."""
        with self._session() as session:
            query = session.query(ClosedMonth.month, ClosedMonth.year)
            cur = require_scope()
            if cur is not None:
                query = query.filter(
                    scoped_campus_filter(session, cur, ClosedMonth.campus_id)
                )
            rows = query.all()
        return {(month, year) for month, year in rows}

"""Fee generation service layer: the core monthly billing mechanic.

A Finance officer (or Admin) picks a Class or All classes, a Month and a Year,
and every student in scope gets one monthly :class:`Charge` summing their
class's fee items, with the item breakdown snapshotted at generation time so
later fee-structure edits never rewrite history. Generation is duplicate-safe
per class+month+year via :class:`GenerationRecord`. Routes are thin adapters
over this module — it is the single testing seam.

Rules that live here:
- Month must be 1-12 and year must be a sensible value (``InvalidPeriod``).
- Only *active* students in a class are billed; archived students keep their
  history and arrears but accrue no new charges.
- Only classes with an itemized fee structure generate; a class with no fee
  items is skipped (or refused, when chosen explicitly) so no zero-dollar
  charges are ever created.
- Completed/Inactive classes are excluded from "All classes" and refused when
  chosen explicitly (``ClassNotActive``).
- A class+month+year can be generated exactly once; a second attempt is refused
  (``AlreadyGenerated``) and never doubles charges. "All classes" re-runs skip
  classes that already have a generation record while generating the rest.
- Every generation (that creates anything) is recorded in the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..classes.service import ClassNotFound
from ..db import Database
from ..models import (
    Charge,
    Class,
    ClassStatus,
    FeeItem,
    GenerationRecord,
    Student,
    StudentStatus,
    User,
)
from ..money import Money, format_cents

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

SKIP_ALREADY_GENERATED = "already generated for this month"
SKIP_NOT_ACTIVE = "class is not active"
SKIP_NO_FEE_ITEMS = "no fee items set up"


class FeeError(Exception):
    """Rejected input or state in a fee-generation operation."""


class InvalidPeriod(FeeError):
    """Month/year fall outside the supported range."""


class AlreadyGenerated(FeeError):
    """The class+month+year already has charges; a re-run would double them."""


class ClassNotActive(FeeError):
    """Fee generation only runs for Active classes."""


class NoFeeItems(FeeError):
    """The class has no fee structure, so there is nothing to bill."""


@dataclass
class ClassGenerationLine:
    """One class's row in a preview: what would be billed, or why not."""

    class_id: int
    class_name: str
    student_count: int
    per_student_cents: Money
    total_cents: Money
    skip_reason: str | None = None

    @property
    def will_generate(self) -> bool:
        return self.skip_reason is None


@dataclass
class GenerationPreview:
    """The per-class breakdown shown in the confirm dialog."""

    month: int
    year: int
    class_id: int | None
    class_name: str | None
    lines: list[ClassGenerationLine]

    @property
    def generatable_lines(self) -> list[ClassGenerationLine]:
        return [line for line in self.lines if line.will_generate]

    @property
    def total_students(self) -> int:
        return sum(line.student_count for line in self.generatable_lines)

    @property
    def total_cents(self) -> Money:
        return sum(line.total_cents for line in self.generatable_lines)


@dataclass
class GeneratedClass:
    """One class actually generated in a run."""

    class_id: int
    class_name: str
    charges_created: int
    per_student_cents: Money
    total_cents: Money


@dataclass
class GenerationResult:
    """What a generation run did: classes generated and classes skipped."""

    month: int
    year: int
    class_id: int | None
    generated: list[GeneratedClass]
    skipped: list[str]

    @property
    def charges_created(self) -> int:
        return sum(line.charges_created for line in self.generated)

    @property
    def total_cents(self) -> Money:
        return sum(line.total_cents for line in self.generated)


class FeeService:
    """Fee generation business rules. Each public method is one unit of work."""

    def __init__(self, db: Database, audit: AuditService | None = None) -> None:
        self._db = db
        self._audit = audit

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @staticmethod
    def _validate_period(month: int, year: int) -> tuple[int, int]:
        if not isinstance(month, int) or not 1 <= month <= 12:
            raise InvalidPeriod("Choose a month between 1 and 12.")
        if not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
            raise InvalidPeriod(f"Choose a year between {MIN_YEAR} and {MAX_YEAR}.")
        return month, year

    @staticmethod
    def _period_label(month: int, year: int) -> str:
        return f"{MONTH_NAMES[month - 1]} {year}"

    @staticmethod
    def _fee_items(session: Session, class_id: int) -> list[FeeItem]:
        return (
            session.query(FeeItem)
            .filter(FeeItem.class_id == class_id)
            .order_by(FeeItem.id)
            .all()
        )

    def _active_students(self, session: Session, class_id: int) -> list[Student]:
        return (
            session.query(Student)
            .filter(
                Student.class_id == class_id,
                Student.status == StudentStatus.ACTIVE,
            )
            .order_by(Student.id)
            .all()
        )

    def _already_generated(self, session: Session, class_id: int, month: int, year: int) -> bool:
        return (
            session.query(GenerationRecord)
            .filter(
                GenerationRecord.class_id == class_id,
                GenerationRecord.month == month,
                GenerationRecord.year == year,
            )
            .first()
            is not None
        )

    def _skip_reason(
        self, session: Session, cls: Class, month: int, year: int, has_items: bool
    ) -> str | None:
        if cls.status != ClassStatus.ACTIVE:
            return SKIP_NOT_ACTIVE
        if not has_items:
            return SKIP_NO_FEE_ITEMS
        if self._already_generated(session, cls.id, month, year):
            return SKIP_ALREADY_GENERATED
        return None

    def _scope(
        self, session: Session, class_id: int | None, month: int, year: int
    ) -> list[ClassGenerationLine]:
        """One line per class in scope, with skip reasons filled in.

        A specific class is always included (even when not active, so the
        caller can be told why). "All classes" includes only Active classes.
        """
        if class_id is not None:
            cls = session.get(Class, class_id)
            if cls is None:
                raise ClassNotFound(f"No class with id {class_id} exists.")
            lines = [cls]
        else:
            lines = (
                session.query(Class)
                .filter(Class.status == ClassStatus.ACTIVE)
                .order_by(Class.created_at, Class.id)
                .all()
            )

        result: list[ClassGenerationLine] = []
        for cls in lines:
            items = self._fee_items(session, cls.id)
            students = self._active_students(session, cls.id)
            per_student = sum(item.amount_cents for item in items)
            result.append(
                ClassGenerationLine(
                    class_id=cls.id,
                    class_name=cls.name,
                    student_count=len(students),
                    per_student_cents=per_student,
                    total_cents=per_student * len(students),
                    skip_reason=self._skip_reason(
                        session, cls, month, year, has_items=bool(items)
                    ),
                )
            )
        return result

    @staticmethod
    def _error_for_reason(reason: str, class_name: str, period: str) -> FeeError:
        if reason == SKIP_ALREADY_GENERATED:
            return AlreadyGenerated(
                f"{class_name} has already been generated for {period}. "
                "No duplicate charges will be created."
            )
        if reason == SKIP_NO_FEE_ITEMS:
            return NoFeeItems(
                f"{class_name} has no fee items set up. "
                "Add its fee structure before generating."
            )
        return ClassNotActive(
            f"{class_name} is not active. Only Active classes generate fees."
        )

    def preview(self, class_id: int | None, month: int, year: int) -> GenerationPreview:
        """The per-class breakdown for the confirm dialog (non-destructive)."""
        month, year = self._validate_period(month, year)
        with self._session() as session:
            lines = self._scope(session, class_id, month, year)
        return GenerationPreview(
            month=month,
            year=year,
            class_id=class_id,
            class_name=lines[0].class_name if class_id is not None else None,
            lines=lines,
        )

    def generate(
        self,
        *,
        user: User | None,
        class_id: int | None,
        month: int,
        year: int,
    ) -> GenerationResult:
        """Generate one monthly charge per active student, duplicate-safe.

        A specific class is refused when it is not active, has no fee items, or
        was already generated for the month (``AlreadyGenerated``). "All
        classes" generates every eligible Active class and skips the rest —
        already-generated or structure-less classes are reported, never doubled.
        All charges and generation records land in one transaction, then one
        audit entry records the run.
        """
        month, year = self._validate_period(month, year)
        period = self._period_label(month, year)

        generated: list[GeneratedClass] = []
        skipped: list[str] = []
        with self._session() as session:
            for line in self._scope(session, class_id, month, year):
                if line.skip_reason is not None:
                    if class_id is not None:
                        raise self._error_for_reason(line.skip_reason, line.class_name, period)
                    skipped.append(f"{line.class_name} — {line.skip_reason}")
                    continue
                items = self._fee_items(session, line.class_id)
                item_snapshot = [
                    {"name": item.name, "amount_cents": item.amount_cents} for item in items
                ]
                for student in self._active_students(session, line.class_id):
                    session.add(
                        Charge(
                            student_id=student.id,
                            month=month,
                            year=year,
                            amount_cents=line.per_student_cents,
                            breakdown=item_snapshot,
                        )
                    )
                session.add(
                    GenerationRecord(
                        class_id=line.class_id, month=month, year=year
                    )
                )
                generated.append(
                    GeneratedClass(
                        class_id=line.class_id,
                        class_name=line.class_name,
                        charges_created=line.student_count,
                        per_student_cents=line.per_student_cents,
                        total_cents=line.total_cents,
                    )
                )
            try:
                session.commit()
            except IntegrityError:
                raise AlreadyGenerated(
                    f"Charges already exist for {period}. No duplicate charges were created."
                ) from None

        if generated:
            class_name = generated[0].class_name if len(generated) == 1 else None
            self._log(user=user, action=AuditActions.FEE_GENERATE, summary=self._summary(
                period=period,
                class_name=class_name,
                generated=generated,
            ))
        return GenerationResult(
            month=month,
            year=year,
            class_id=class_id,
            generated=generated,
            skipped=skipped,
        )

    @staticmethod
    def _summary(
        *,
        period: str,
        class_name: str | None,
        generated: list[GeneratedClass],
    ) -> str:
        total_cents = sum(line.total_cents for line in generated)
        charges = sum(line.charges_created for line in generated)
        if class_name is not None:
            return (
                f"Generated {period} fees for {class_name}: "
                f"{charges} charge(s), {format_cents(total_cents)}"
            )
        classes_word = "class" if len(generated) == 1 else "classes"
        return (
            f"Generated {period} fees for all classes: {len(generated)} {classes_word}, "
            f"{charges} charge(s), {format_cents(total_cents)}"
        )

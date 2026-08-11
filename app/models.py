"""Domain model for the school finance app.

Schema is created via ``Base.metadata.create_all`` on startup (migrations are out
of scope for v1). All amounts are integer cents — never floats (see ``app.money``).
There are no hard deletes: everything destructive-looking is a status transition.

Fee billing is **derived from enrollment** (see ``CONTEXT.md`` — "Fee billing"):
a student owes from their ``enrolled_on`` month through their ``archived_on``
month (service-through-period-end), excluding ``ClosedMonth`` rows, while active.
The monthly obligation is a ``FeeTemplate`` amount (linked or custom) minus any
stacked ``Waiver`` rows for that month, and ``Payment`` rows carry a month+year
tag for the expected-vs-paid comparison. Amounts are **effective-dated**
(FW-20): a change carries an effective month, recorded as a per-student
``StudentAmountChange`` row, and a past month's amount is never rewritten.
There are no charge rows and no generation step.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC now (SQLite-safe) for created_at defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """The current local calendar date (SQLite-safe) for enrollment defaults."""
    return date.today()


class Base(DeclarativeBase):
    pass


class UserRoles:
    ADMIN = "admin"
    FINANCE = "finance"


class ClassStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    INACTIVE = "inactive"


class StudentStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"


class PaymentMethods:
    CASH = "cash"
    BANK = "bank"
    OTHER = "other"


class SchoolProfile(Base):
    """The school's identity — a single row (id always 1).

    ``school_name`` is always required; the contact fields are optional free
    text. ``logo_filename`` names the uploaded logo file, which lives next to
    the app data (see docs/adr/0001-logo-in-data-dir.md).
    """

    __tablename__ = "school_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    logo_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRoles.FINANCE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AuthSession(Base):
    """Server-side session. The cookie only holds the random token; the session
    row is revocable (logout) and expiring."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ClassStatus.ACTIVE)
    # The class's default FeeTemplate — the amount a newly added student is
    # expected to pay each month (replaces the old per-class fee items, FW-7).
    default_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("fee_templates.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    default_template: Mapped[FeeTemplate | None] = relationship()
    students: Mapped[list[Student]] = relationship(back_populates="school_class")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=StudentStatus.ACTIVE)
    # The first owed month is the month of ``enrolled_on`` (default today,
    # back-datable); ``archived_on`` marks the last owed month
    # (service-through-period-end, FW-14) and is captured when archiving.
    enrolled_on: Mapped[date] = mapped_column(Date, nullable=False, default=today)
    archived_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The linked FeeTemplate (FW-7): template amount raises propagate to every
    # student linked here. A null link means the student holds a custom amount.
    fee_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("fee_templates.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    school_class: Mapped[Class] = relationship(back_populates="students")
    fee_template: Mapped[FeeTemplate | None] = relationship(back_populates="students")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class FeeTemplate(Base):
    """A named monthly amount (e.g. "Standard — $100") a class defaults to and a
    student can be linked to. Defines what a linked student is expected to pay
    each month (``CONTEXT.md`` — "Fee Template").

    Archiving (``archived``) is the "remove": the row and its linkage stay, but
    the template stops appearing in pickers (no hard deletes). An amount change
    is effective-dated (FW-20): linked students get a :class:`StudentAmountChange`
    row so past months keep the amount in force then.
    """

    __tablename__ = "fee_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    students: Mapped[list[Student]] = relationship(back_populates="fee_template")


class StudentAmountChange(Base):
    """An effective-dated amount for one student (FW-20).

    ``amount_cents`` is what the student is expected to pay from ``month``/``year``
    onward. Template amount raises write one row per linked student (ticket 02);
    a month's expected amount is the last change effective on or before that
    month, so past months are never rewritten by a later change.
    """

    __tablename__ = "student_amount_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()


class Waiver(Base):
    """Per-(student, month) forgiveness reducing that month's expected amount.

    Multiple waivers stack on the same month; a month's expected is
    ``amount in force - total waivers``, never below zero. The acting user is
    recorded (``created_by``) and the reason is required (``label``).
    """

    __tablename__ = "waivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()


class ClosedMonth(Base):
    """A month the whole school is closed: excluded from every student's owed
    months, so it never appears as unpaid (FW-17)."""

    __tablename__ = "closed_months"
    __table_args__ = (
        UniqueConstraint("month", "year", name="uq_closed_month_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Payment(Base):
    """A month-tagged payment (FW-16): recorded against a specific month+year.

    Any month may be tagged — not limited to the student's owed range — and the
    expected-vs-paid comparison happens per month. Excess over a month's expected
    rolls forward as ``Credit`` (FW-15/FW-21).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentMethods.CASH)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    # The month tag — the clerk's entry on the record screen.
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()


class Credit(Base):
    """Overpayment carried on a student's account (no refunds in v1)."""

    __tablename__ = "credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    # Archiving is the "remove": the row and its expenses stay, but the category
    # stops appearing in the record dropdown (no hard deletes — see module docstring).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentMethods.CASH)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    category: Mapped[ExpenseCategory] = relationship()


class AuditLogEntry(Base):
    """Append-only audit trail. No UI path edits or deletes these rows."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    user: Mapped[User | None] = relationship()

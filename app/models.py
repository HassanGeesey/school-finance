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

Multi-school / multi-campus (cloud path): a School is the umbrella holding
one or more Campuses, and the Campus is the fully self-contained operational
unit (``docs/adr/0003``). Every operational data table is scoped by a mandatory
``campus_id`` (NOT NULL, ticket 09) — the School is reached via the campus →
school join — while the audit log keeps a nullable campus for school-level
actions (MD-2). Users
carry a scope: ``school_id`` for Superadmin/Owner, ``campus_id`` for
Admin/Finance. The offline .exe keeps the single-school model: a fresh install
bootstraps one implicit School + Campus silently. The Campus owns the identity
(per-Campus branding, multi-school ticket 07): name, logo, and contact fields
live on the ``campuses`` row, and the legacy single-row ``school_profile`` has
been retired from the model.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
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
    SUPERADMIN = "superadmin"
    OWNER = "owner"


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


class School(Base):
    """An organization the app serves — the umbrella one or more Campuses
    belong to (``CONTEXT.md`` — "Schools & campuses").

    On the offline path a fresh install bootstraps one School silently (with a
    single Campus) so existing behavior is unchanged; the setup wizard names
    that implicit Campus, which carries the school's identity (multi-school
    ticket 07). The cloud setup wizard names the School itself; its Superadmin
    creates Campuses later from the School Dashboard (ticket 05).
    """

    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    campuses: Mapped[list[Campus]] = relationship(back_populates="school")


class Campus(Base):
    """A branch of a School (1..N) — the fully self-contained operational unit.

    Owns the per-Campus profile shape (multi-school ticket 07): name, logo, and
    contact fields are the identity rendered on receipts, statements, the
    sidebar, the tab title, and the footer. Plus the archive flag: an archived
    Campus keeps its history but stops being active (soft delete — no hard
    deletes anywhere in the tenant tables).
    """

    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    logo_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    school: Mapped[School] = relationship(back_populates="campuses")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRoles.FINANCE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Tenant scope (MD-2): Superadmin and Owner scope by school; Admin and
    # Finance scope by campus. One of the two is set per user. Both stay
    # nullable while the single-school path scopes by nothing (ticket 01 is
    # additive only).
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AuthSession(Base):
    """Server-side session. The cookie only holds the random token; the session
    row is revocable (logout) and expiring."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ClassStatus.ACTIVE)
    # The class's default FeeTemplate — the amount a newly added student is
    # expected to pay each month (replaces the old per-class fee items, FW-7).
    default_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("fee_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    default_template: Mapped[FeeTemplate | None] = relationship()
    students: Mapped[list[Student]] = relationship(back_populates="school_class")
    campus: Mapped[Campus] = relationship()


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
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
        ForeignKey("fee_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    school_class: Mapped[Class] = relationship(back_populates="students")
    fee_template: Mapped[FeeTemplate | None] = relationship(back_populates="students")
    campus: Mapped[Campus] = relationship()

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
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    students: Mapped[list[Student]] = relationship(back_populates="fee_template")
    campus: Mapped[Campus] = relationship()


class StudentAmountChange(Base):
    """An effective-dated amount for one student (FW-20).

    ``amount_cents`` is what the student is expected to pay from ``month``/``year``
    onward. Template amount raises write one row per linked student (ticket 02);
    a month's expected amount is the last change effective on or before that
    month, so past months are never rewritten by a later change.
    """

    __tablename__ = "student_amount_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()
    campus: Mapped[Campus] = relationship()


class Waiver(Base):
    """Per-(student, month) forgiveness reducing that month's expected amount.

    Multiple waivers stack on the same month; a month's expected is
    ``amount in force - total waivers``, never below zero. The acting user is
    recorded (``created_by``) and the reason is required (``label``).
    """

    __tablename__ = "waivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()
    campus: Mapped[Campus] = relationship()


class ClosedMonth(Base):
    """A month the campus is closed: excluded from every student's owed
    months, so it never appears as unpaid (FW-17).

    Per-Campus (MD-3): each branch sets its own holidays, so uniqueness is per
    (campus_id, month, year). ``campus_id`` is mandatory (ticket 09).
    """

    __tablename__ = "closed_months"
    __table_args__ = (
        UniqueConstraint("campus_id", "month", "year", name="uq_closed_month_campus_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    campus: Mapped[Campus] = relationship()


class Payment(Base):
    """A month-tagged payment (FW-16): recorded against a specific month+year.

    Any month may be tagged — not limited to the student's owed range — and the
    expected-vs-paid comparison happens per month. Excess over a month's expected
    rolls forward as ``Credit`` (FW-15/FW-21).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentMethods.CASH)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    # The month tag — the clerk's entry on the record screen.
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()
    campus: Mapped[Campus] = relationship()


class Credit(Base):
    """Overpayment carried on a student's account (no refunds in v1)."""

    __tablename__ = "credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    campus: Mapped[Campus] = relationship()


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        UniqueConstraint("campus_id", "name", name="uq_expense_categories_campus_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Archiving is the "remove": the row and its expenses stay, but the category
    # stops appearing in the record dropdown (no hard deletes — see module docstring).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    campus: Mapped[Campus] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentMethods.CASH)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    category: Mapped[ExpenseCategory] = relationship()
    campus: Mapped[Campus] = relationship()


class AuditLogEntry(Base):
    """Append-only audit trail. No UI path edits or deletes these rows."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: school-level actions (campus creation, admin assignment, owner
    # management) are recorded school-wide, not under a single campus (MD-2).
    campus_id: Mapped[int | None] = mapped_column(ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    user: Mapped[User | None] = relationship()
    campus: Mapped[Campus | None] = relationship()

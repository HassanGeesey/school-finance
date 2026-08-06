"""Domain model for the school finance app.

Schema is created via ``Base.metadata.create_all`` on startup (migrations are out
of scope for v1). All amounts are integer cents — never floats (see ``app.money``).
There are no hard deletes: everything destructive-looking is a status transition.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
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


class AdjustmentKinds:
    EXTRA = "extra"
    WAIVER = "waiver"


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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    fee_items: Mapped[list[FeeItem]] = relationship(
        back_populates="school_class", cascade="all, delete-orphan"
    )
    students: Mapped[list[Student]] = relationship(back_populates="school_class")


class FeeItem(Base):
    __tablename__ = "fee_items"
    __table_args__ = (UniqueConstraint("class_id", "name", name="uq_fee_item_class_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    school_class: Mapped[Class] = relationship(back_populates="fee_items")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=StudentStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    school_class: Mapped[Class] = relationship(back_populates="students")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Charge(Base):
    __tablename__ = "charges"
    __table_args__ = (
        UniqueConstraint("student_id", "month", "year", name="uq_charge_student_month_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # Item breakdown snapshotted at generation time so later fee-structure edits
    # never rewrite history. e.g. [{"name": "Tuition", "amount_cents": 50000}]
    breakdown: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()
    adjustments: Mapped[list[Adjustment]] = relationship(
        back_populates="charge", cascade="all, delete-orphan"
    )


class Adjustment(Base):
    __tablename__ = "adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    charge_id: Mapped[int] = mapped_column(ForeignKey("charges.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # extra | waiver
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    charge: Mapped[Charge] = relationship(back_populates="adjustments")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentMethods.CASH)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    student: Mapped[Student] = relationship()
    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentAllocation(Base):
    """How a payment was split across the student's unpaid charges."""

    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False, index=True)
    charge_id: Mapped[int] = mapped_column(ForeignKey("charges.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="allocations")
    charge: Mapped[Charge] = relationship()


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


class GenerationRecord(Base):
    """Marks a class+month+year as already generated (duplicate-safety)."""

    __tablename__ = "generation_records"
    __table_args__ = (
        UniqueConstraint("class_id", "month", "year", name="uq_generation_class_month_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

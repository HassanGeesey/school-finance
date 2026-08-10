"""Classes & fee-structure service layer.

Business rules for the Admin's configuration surface: classes (create/rename/
status) and each class's itemized fee structure (add/edit/remove fee items).
Routes are thin adapters over this module — it is the single testing seam.

Rules that live here:
- A class name is required; status is one of active/completed/inactive.
- Completed/Inactive classes keep their records but stop generating fees later
  (enforced in the fee-generation feature); they can be reopened here.
- Fee item amounts are positive integer cents (``app.money``), never floats.
- A fee item name is unique within its class (case-insensitive).
- Every change is recorded in the audit log with the acting user.
- There are no hard deletes: a class is never destroyed, and removing a fee item
  only stops it from being billed in future months — generated charges snapshot
  their item breakdown, so history is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import Class, ClassStatus, FeeItem, Student, User
from ..money import AmountInput, Money, format_cents, to_cents

CLASS_STATUS_LABELS = {
    ClassStatus.ACTIVE: "Active",
    ClassStatus.COMPLETED: "Completed",
    ClassStatus.INACTIVE: "Inactive",
}

VALID_STATUSES = set(CLASS_STATUS_LABELS)


class ClassError(Exception):
    """Rejected input or state in a class/fee-structure operation."""


class ClassNotFound(ClassError):
    """No class exists with the given id."""


class FeeItemNotFound(ClassError):
    """No fee item exists with the given id, or it does not belong to the given class."""


class DuplicateFeeItemName(ClassError):
    """The class already has a fee item with that name."""


@dataclass
class ClassSummary:
    """One class with its fee structure and the resulting monthly fee per student."""

    cls: Class
    items: list[FeeItem]
    item_count: int
    monthly_total_cents: Money


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

    @staticmethod
    def _validate_amount(amount: AmountInput) -> int:
        try:
            cents = to_cents(amount)
        except (TypeError, ValueError):
            raise ClassError("Enter a valid amount.") from None
        if cents <= 0:
            raise ClassError("Amount must be greater than zero.")
        return cents

    def create_class(
        self,
        *,
        user: User | None,
        name: str,
        status: str = ClassStatus.ACTIVE,
    ) -> Class:
        """Create a class. Names are required; status defaults to Active."""
        name = self._validate_name(name, "Class name")
        status = self._validate_status(status)

        with self._session() as session:
            cls = Class(name=name, status=status)
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

    def get_class(self, class_id: int) -> Class:
        with self._session() as session:
            return self._get_class(session, class_id)

    def class_summary(self, class_id: int) -> ClassSummary:
        """One class with its fee items and the monthly fee per student (sum of items)."""
        with self._session() as session:
            cls = self._get_class(session, class_id)
            items = session.query(FeeItem).filter(FeeItem.class_id == class_id).all()
        return self._to_summary(cls, items)

    def list_class_summaries(self) -> list[ClassSummary]:
        """Every class with its fee-structure summary, oldest first."""
        with self._session() as session:
            classes = session.query(Class).order_by(Class.created_at, Class.id).all()
            items = session.query(FeeItem).order_by(FeeItem.class_id, FeeItem.id).all()
            items_by_class: dict[int, list[FeeItem]] = {}
            for item in items:
                items_by_class.setdefault(item.class_id, []).append(item)
            return [self._to_summary(cls, items_by_class.get(cls.id, [])) for cls in classes]

    @staticmethod
    def _to_summary(cls: Class, items: list[FeeItem]) -> ClassSummary:
        return ClassSummary(
            cls=cls,
            items=items,
            item_count=len(items),
            monthly_total_cents=sum(item.amount_cents for item in items),
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

    def _fee_item_name_taken(
        self, session: Session, class_id: int, name: str, exclude_item_id: int | None = None
    ) -> bool:
        for item in session.query(FeeItem).filter(FeeItem.class_id == class_id).all():
            if item.id == exclude_item_id:
                continue
            if item.name == name:
                return True
        return False

    def add_fee_item(
        self,
        *,
        user: User | None,
        class_id: int,
        name: str,
        amount: AmountInput,
    ) -> FeeItem:
        name = self._validate_name(name, "Fee item name")
        amount_cents = self._validate_amount(amount)

        with self._session() as session:
            cls = self._get_class(session, class_id)
            if self._fee_item_name_taken(session, class_id, name):
                raise DuplicateFeeItemName(
                    f"This class already has a fee item named '{name}'."
                )
            item = FeeItem(class_id=class_id, name=name, amount_cents=amount_cents)
            session.add(item)
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateFeeItemName(
                    f"This class already has a fee item named '{name}'."
                ) from None
            session.refresh(item)
        self._log(
            user=user,
            action=AuditActions.FEE_ITEM_ADD,
            summary=f"Added fee item {item.name} ({format_cents(item.amount_cents)}) to class {cls.name}",
        )
        return item

    def update_fee_item(
        self,
        *,
        user: User | None,
        class_id: int,
        item_id: int,
        name: str,
        amount: AmountInput,
    ) -> FeeItem:
        name = self._validate_name(name, "Fee item name")
        amount_cents = self._validate_amount(amount)

        with self._session() as session:
            item = session.get(FeeItem, item_id)
            if item is None:
                raise FeeItemNotFound(f"No fee item with id {item_id} exists.")
            if item.class_id != class_id:
                raise FeeItemNotFound(
                    f"Fee item {item_id} does not belong to class {class_id}."
                )
            if self._fee_item_name_taken(session, class_id, name, exclude_item_id=item.id):
                raise DuplicateFeeItemName(
                    f"This class already has a fee item named '{name}'."
                )
            if item.name == name and item.amount_cents == amount_cents:
                return item
            class_name = item.school_class.name
            old = f"{item.name} ({format_cents(item.amount_cents)})"
            item.name = name
            item.amount_cents = amount_cents
            new = f"{name} ({format_cents(amount_cents)})"
            try:
                session.commit()
            except IntegrityError:
                raise DuplicateFeeItemName(
                    f"This class already has a fee item named '{name}'."
                ) from None
            session.refresh(item)
        self._log(
            user=user,
            action=AuditActions.FEE_ITEM_UPDATE,
            summary=f"Updated fee item in class {class_name}: {old} -> {new}",
        )
        return item

    def remove_fee_item(
        self, *, user: User | None, class_id: int, item_id: int
    ) -> None:
        with self._session() as session:
            item = session.get(FeeItem, item_id)
            if item is None:
                raise FeeItemNotFound(f"No fee item with id {item_id} exists.")
            if item.class_id != class_id:
                raise FeeItemNotFound(
                    f"Fee item {item_id} does not belong to class {class_id}."
                )
            class_name = item.school_class.name
            item_name = item.name
            session.delete(item)
            session.commit()
        self._log(
            user=user,
            action=AuditActions.FEE_ITEM_REMOVE,
            summary=f"Removed fee item {item_name} from class {class_name}",
        )

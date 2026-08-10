"""Seed the school finance app with realistic demo data.

Run from the repo root::

    .venv\\Scripts\\python.exe scripts\\seed_demo.py            # seed an empty database
    .venv\\Scripts\\python.exe scripts\\seed_demo.py --reset    # wipe demo data, then seed

Everything is written through the app's own services, so every row lands via
the real business rules (validation, oldest-unpaid-first allocation, audit
trail). Created data:

- A school profile plus an ``admin`` / ``finance`` login (only when missing).
- Four classes (Grade 4-7) with itemized fee structures.
- ~42 students with East African names.
- Four months of generated fees, with a deliberate spread of payments:
  fully paid, one/two months behind, half-paid, and never-paid students — so
  the arrears page shows current, amber, and red debts.
- Expense categories and several months of expenses.

``--reset`` deletes all *domain* data (classes, students, charges, payments,
expenses, ...). It never touches users, the school profile, or the append-only
audit log.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.admin.service import AdminUserService
from app.audit.service import AuditService
from app.classes.service import ClassService
from app.config import settings
from app.db import Database, make_engine
from app.expenses.service import ExpenseService
from app.fees.service import FeeService
from app.models import (
    Adjustment,
    Charge,
    Class,
    Credit,
    Expense,
    ExpenseCategory,
    FeeItem,
    GenerationRecord,
    Payment,
    PaymentAllocation,
    Student,
    User,
    UserRoles,
)
from app.payments.service import PaymentService
from app.profile.service import ProfileService
from app.students.service import StudentService

ADMIN_LOGIN = ("admin", "admin123")
FINANCE_LOGIN = ("finance", "finance123")

# Class name -> [(fee item, amount), ...]
CLASSES = {
    "Grade 4": [("Tuition", "100.00"), ("Boarding", "40.00")],
    "Grade 5": [("Tuition", "110.00"), ("Boarding", "40.00")],
    "Grade 6": [("Tuition", "120.00"), ("Boarding", "40.00")],
    "Grade 7": [("Tuition", "130.00"), ("Boarding", "40.00")],
}

# (first, last) name pairs assigned round-robin across classes.
STUDENTS = [
    ("Atieno", "Odhiambo"), ("Brian", "Mwangi"), ("Cynthia", "Achieng"),
    ("David", "Otieno"), ("Faith", "Njeri"), ("George", "Kiprop"),
    ("Grace", "Wanjiku"), ("Hassan", "Abdi"), ("Ibrahim", "Hassan"),
    ("Jane", "Kamau"), ("Kevin", "Onyango"), ("Linet", "Cherono"),
    ("Mercy", "Chebet"), ("Naomi", "Wambui"), ("Peter", "Kibet"),
    ("Queenie", "Auma"), ("Ruth", "Wairimu"), ("Samuel", "Ochieng"),
    ("Teresia", "Nyambura"), ("Victor", "Omondi"), ("Winnie", "Achieng"),
    ("Zawadi", "Mwende"), ("Alvin", "Ochieng"), ("Betty", "Chepkoech"),
    ("Collins", "Kipchirchir"), ("Diana", "Akinyi"), ("Edwin", "Kiptoo"),
    ("Florence", "Auma"), ("Gideon", "Rotich"), ("Hilda", "Nyawira"),
    ("Isaac", "Kipngeno"), ("Joyce", "Wanjala"), ("Kelvin", "Odhiambo"),
    ("Lucy", "Achieng"), ("Michael", "Ndegwa"), ("Nancy", "Achieng"),
    ("Oscar", "Kipkorir"), ("Pauline", "Atieno"), ("Rodgers", "Omollo"),
    ("Sharon", "Chebet"), ("Timothy", "Kiprono"), ("Veronica", "Achieng"),
]

EXPENSE_CATEGORIES = ["Salaries", "Utilities", "Supplies", "Maintenance", "Transport"]

# (category, description, amount, method, day-of-month)
MONTHLY_EXPENSES = [
    ("Salaries", "Staff salaries", "1850.00", "bank", 28),
    ("Utilities", "Electricity bill", "450.00", "bank", 12),
    ("Supplies", "Exercise books (Grade 4-6)", "320.00", "cash", 15),
    ("Transport", "School bus fuel", "180.00", "bank", 6),
]
BI_MONTHLY_EXPENSES = [
    ("Maintenance", "Classroom roof repair", "240.00", "cash", 20),
]


def _recent_periods(today: date, count: int = 4) -> list[tuple[int, int]]:
    """The last ``count`` month/year pairs, oldest first."""
    start = today.year * 12 + (today.month - 1) - (count - 1)
    return [
        ((start + offset) // 12, (start + offset) % 12 + 1)
        for offset in range(count)
    ]


def _safe_day(today: date, year: int, month: int, day: int) -> date:
    """A date that is never in the future (current-month days are clamped)."""
    if (year, month) == (today.year, today.month):
        day = min(day, today.day)
    return date(year, month, day)


def _profile_for(index: int) -> str:
    """Payment pattern per student, deterministic mix."""
    if index % 10 == 0:
        return "unpaid"
    if index % 7 == 1:
        return "partial"
    if index % 13 == 4:
        return "two_behind"
    if index % 5 == 3:
        return "one_behind"
    return "current"


class Seeder:
    def __init__(self, db: Database) -> None:
        audit = AuditService(db)
        self.db = db
        self.today = date.today()
        self.admin = AdminUserService(db, audit=audit)
        self.classes = ClassService(db, audit=audit)
        self.students = StudentService(db, audit=audit)
        self.fees = FeeService(db, audit=audit)
        self.payments = PaymentService(db, audit=audit)
        self.expenses = ExpenseService(db, audit=audit)
        self.profile = ProfileService(db, audit=audit, logos=None)

    # ------------------------------------------------------------------ infra

    def ensure_users_and_profile(self) -> User:
        with self.db.session() as session:
            admin = (
                session.query(User)
                .filter_by(role=UserRoles.ADMIN)
                .order_by(User.id)
                .first()
            )
        if admin is None:
            admin = self.admin.create_user(
                actor=None,
                name="Head Teacher",
                username=ADMIN_LOGIN[0],
                password=ADMIN_LOGIN[1],
                role=UserRoles.ADMIN,
            )
            print(f"Created admin login: {ADMIN_LOGIN[0]} / {ADMIN_LOGIN[1]}")
        with self.db.session() as session:
            finance = (
                session.query(User)
                .filter_by(role=UserRoles.FINANCE)
                .order_by(User.id)
                .first()
            )
        if finance is None:
            self.admin.create_user(
                actor=admin,
                name="Finance Officer",
                username=FINANCE_LOGIN[0],
                password=FINANCE_LOGIN[1],
                role=UserRoles.FINANCE,
            )
            print(f"Created finance login: {FINANCE_LOGIN[0]} / {FINANCE_LOGIN[1]}")

        current = self.profile.get_profile()
        if not current.school_name:
            self.profile.update_profile(
                user=admin,
                school_name="Baidoa Bedrock Academy",
                address="Tifan area, Baidoa",
                phone="+252 61 555 1234",
                email="accounts@baidoabedrock.edu",
                website="https://baidoabedrock.edu",
            )
            print("Created school profile: Baidoa Bedrock Academy")
        return admin

    # ------------------------------------------------------------------ domain

    def seed_classes_and_students(self, actor: User) -> dict[str, int]:
        class_ids: dict[str, int] = {}
        students_by_class: dict[int, list[Student]] = {}
        counts = {"Grade 4": 12, "Grade 5": 11, "Grade 6": 10, "Grade 7": 9}
        index = 0
        for name, items in CLASSES.items():
            cls = self.classes.create_class(user=actor, name=name)
            class_ids[name] = cls.id
            for item_name, amount in items:
                self.classes.add_fee_item(
                    user=actor, class_id=cls.id, name=item_name, amount=amount
                )
            students_by_class[cls.id] = []
            for _ in range(counts[name]):
                first, last = STUDENTS[index]
                index += 1
                student = self.students.add_student(
                    user=actor, class_id=cls.id, first_name=first, last_name=last
                )
                students_by_class[cls.id].append(student)
        return class_ids

    def complete_grade7(self, actor: User) -> None:
        """Mark Grade 7 completed after its bills were generated (retains arrears)."""
        with self.db.session() as session:
            cls = session.query(Class).filter(Class.name == "Grade 7").first()
        if cls is not None and cls.status != "completed":
            self.classes.update_class(
                user=actor, class_id=cls.id, name=cls.name, status="completed"
            )

    def seed_charges(self, actor: User) -> None:
        with self.db.session() as session:
            class_ids = [cls.id for cls in session.query(Class).all()]
        for period in _recent_periods(self.today):
            year, month = period
            for class_id in class_ids:
                self.fees.generate(user=actor, class_id=class_id, month=month, year=year)

    def seed_payments(self, actor: User) -> None:
        methods = ["cash", "bank", "other"]
        with self.db.session() as session:
            students = (
                session.query(Student)
                .order_by(Student.class_id, Student.id)
                .all()
            )
            monthly_by_class = {
                cls.id: self._monthly_fee_cents(session, cls.id)
                for cls in session.query(Class).all()
            }
        periods = _recent_periods(self.today)
        for position, student in enumerate(students):
            monthly = monthly_by_class[student.class_id]
            profile = _profile_for(position)
            for offset, (year, month) in enumerate(periods):
                if profile == "unpaid":
                    continue
                if profile == "one_behind" and offset == len(periods) - 1:
                    continue
                if profile == "two_behind" and offset >= len(periods) - 2:
                    continue
                if profile == "partial":
                    cents = int(monthly * 0.5)
                else:
                    cents = monthly
                self.payments.record_payment(
                    user=actor,
                    student_id=student.id,
                    amount=f"{cents / 100:.2f}",
                    method=methods[position % len(methods)],
                    paid_on=_safe_day(
                        self.today, year, month, 3 + position % 3
                    ),
                )

    def seed_expenses(self, actor: User) -> None:
        category_ids: dict[str, int] = {}
        for name in EXPENSE_CATEGORIES:
            category = self.expenses.create_category(user=actor, name=name)
            category_ids[name] = category.id
        for offset, (year, month) in enumerate(_recent_periods(self.today)):
            plan = list(MONTHLY_EXPENSES)
            if offset % 2 == 0:
                plan = plan + BI_MONTHLY_EXPENSES
            for category, description, amount, method, day in plan:
                self.expenses.record_expense(
                    user=actor,
                    category_id=category_ids[category],
                    description=description,
                    amount=amount,
                    method=method,
                    occurred_on=_safe_day(self.today, year, month, day),
                )

    def archive_a_student(self, actor: User) -> None:
        """Leave one never-paying student archived but still in arrears."""
        with self.db.session() as session:
            student = (
                session.query(Student)
                .order_by(Student.id)
                .filter(Student.status == "active")
                .first()
            )
            if student is not None:
                self.students.archive_student(user=actor, student_id=student.id)

    @staticmethod
    def _monthly_fee_cents(session, class_id: int) -> int:
        total = (
            session.query(func.sum(FeeItem.amount_cents))
            .filter(FeeItem.class_id == class_id)
            .scalar()
        )
        return int(total or 0)

    # ------------------------------------------------------------------ report

    def summary(self) -> None:
        from app.arrears.service import ArrearsService

        with self.db.session() as session:
            students = session.query(Student).count()
            charges = session.query(Charge).count()
            payments = session.query(Payment).count()
            expenses = session.query(Expense).count()
            categories = session.query(ExpenseCategory).count()
        arrears_lines = len(ArrearsService(self.db).arrears_report())
        print(
            f"Seeded: {len(CLASSES)} classes, {students} students, "
            f"{charges} charges, {payments} payments, "
            f"{categories} expense categories, {expenses} expenses, "
            f"{arrears_lines} student(s) in arrears."
        )


def reset_domain(db: Database) -> None:
    """Delete demo domain data (never users, profile, or audit)."""
    with db.session() as session:
        session.query(PaymentAllocation).delete()
        session.query(Credit).delete()
        session.query(Payment).delete()
        session.query(Adjustment).delete()
        session.query(Charge).delete()
        session.query(GenerationRecord).delete()
        session.query(Expense).delete()
        session.query(ExpenseCategory).delete()
        session.query(FeeItem).delete()
        session.query(Student).delete()
        session.query(Class).delete()
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the school finance demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing domain data before seeding.",
    )
    args = parser.parse_args()

    db = Database(make_engine(settings.DATABASE_URL))
    db.create_all()

    with db.session() as session:
        already = session.query(Class).first() is not None
    if already and not args.reset:
        print(
            "The database already has classes. Re-run with --reset to wipe "
            "demo data first, or skip seeding."
        )
        return

    if args.reset:
        reset_domain(db)
        print("Reset domain data.")

    seeder = Seeder(db)
    actor = seeder.ensure_users_and_profile()
    seeder.seed_classes_and_students(actor)
    seeder.seed_charges(actor)
    seeder.complete_grade7(actor)
    seeder.seed_payments(actor)
    seeder.seed_expenses(actor)
    seeder.archive_a_student(actor)
    seeder.summary()
    print("Done. Start the app (run.bat) and log in with admin/admin123.")


if __name__ == "__main__":
    main()

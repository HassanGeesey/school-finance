"""Seed the school finance app with realistic demo data.

Run from the repo root::

    .venv\\Scripts\\python.exe scripts\\seed_demo.py            # seed an empty database
    .venv\\Scripts\\python.exe scripts\\seed_demo.py --reset    # wipe demo data, then seed

Everything is written through the app's own services, so every row lands via
the real business rules (validation, oldest-unpaid-first credit, audit trail).
Created data:

- A school profile plus an ``admin`` / ``finance`` login (only when missing).
- Four fee templates (Grade 4-7) and four classes defaulting to them.
- ~42 students with East African names, enrolled at the start of the seeding
  window and linked to their class template.
- Four owed months of derived billing with a deliberate spread of month-tagged
  payments: fully paid, one/two months behind, half-paid, never-paid, and one
  overpaying student whose excess rolls forward as credit — so the arrears page
  shows current, amber, and red debts.
- A full-month waiver for the archived student's newest owed month.
- Expense categories and several months of expenses.

``--reset`` deletes all *domain* data (templates, classes, students, payments,
credits, waivers, expenses, ...). It never touches users, the campus identity,
or the append-only audit log.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.admin.service import AdminUserService
from app.audit.service import AuditService
from app.classes.service import ClassService
from app.config import settings
from app.db import Database, make_engine
from app.expenses.service import ExpenseService
from app.fees.service import TemplateService, WaiverService
from app.models import (
    Campus,
    Class,
    ClosedMonth,
    Credit,
    Expense,
    ExpenseCategory,
    FeeTemplate,
    Payment,
    Student,
    StudentAmountChange,
    User,
    UserRoles,
    Waiver,
)
from app.payments.service import PaymentService
from app.profile.service import ProfileService
from app.students.service import StudentService
from app.tenants.service import ensure_bootstrap_on

ADMIN_LOGIN = ("admin", "admin123")
FINANCE_LOGIN = ("finance", "finance123")

# Grade name -> (fee template name, monthly amount)
TEMPLATES = {
    "Grade 4": ("Grade 4 — Full fee", "140.00"),
    "Grade 5": ("Grade 5 — Full fee", "150.00"),
    "Grade 6": ("Grade 6 — Full fee", "160.00"),
    "Grade 7": ("Grade 7 — Full fee", "170.00"),
}

# Class name -> number of students seeded into it.
CLASS_STUDENT_COUNTS = {"Grade 4": 12, "Grade 5": 11, "Grade 6": 10, "Grade 7": 9}

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


def _enrollment_start(today: date) -> date:
    """The first day of the oldest period — every student is enrolled then."""
    year, month = _recent_periods(today)[0]
    return date(year, month, 1)


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
    if index % 17 == 8:
        return "credit"
    return "current"


class Seeder:
    def __init__(self, db: Database) -> None:
        audit = AuditService(db)
        self.db = db
        self.today = date.today()
        self.admin = AdminUserService(db, audit=audit)
        self.classes = ClassService(db, audit=audit)
        self.students = StudentService(db, audit=audit)
        self.templates = TemplateService(db, audit=audit)
        self.waivers = WaiverService(db, audit=audit)
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

        # The offline app's implicit School + Campus (the same bootstrap the
        # setup wizard uses) is where the demo identity lives. The admin is
        # bound to it so the scoped profile and operational services see it.
        with self.db.session() as session:
            _school, campus = ensure_bootstrap_on(session)
            admin = session.get(User, admin.id)
            if admin.school_id != _school.id or admin.campus_id != campus.id:
                admin.school_id = _school.id
                admin.campus_id = campus.id
            session.commit()

        current = self.profile.get_profile(campus=campus)
        if not current or not current.name:
            self.profile.update_profile(
                user=admin,
                campus=campus,
                school_name="Baidoa Bedrock Academy",
                address="Tifan area, Baidoa",
                phone="+252 61 555 1234",
                email="accounts@baidoabedrock.edu",
                website="https://baidoabedrock.edu",
            )
            print("Created campus profile: Baidoa Bedrock Academy")
        return admin

    # ------------------------------------------------------------------ domain

    def seed_templates(self, actor: User) -> dict[str, int]:
        ids: dict[str, int] = {}
        for grade, (name, amount) in TEMPLATES.items():
            template = self.templates.create_template(user=actor, name=name, amount=amount)
            ids[grade] = template.id
        return ids

    def seed_classes_and_students(self, actor: User, template_ids: dict[str, int]) -> None:
        enrolled = _enrollment_start(self.today)
        index = 0
        for grade, count in CLASS_STUDENT_COUNTS.items():
            cls = self.classes.create_class(
                user=actor, name=grade, default_template_id=template_ids[grade]
            )
            for _ in range(count):
                first, last = STUDENTS[index]
                index += 1
                self.students.add_student(
                    user=actor,
                    class_id=cls.id,
                    first_name=first,
                    last_name=last,
                    enrolled_on=enrolled,
                    fee_template_id=template_ids[grade],
                )

    def complete_grade7(self, actor: User) -> None:
        """Mark Grade 7 completed (keeps its students' owed months and arrears)."""
        with self.db.session() as session:
            cls = session.query(Class).filter(Class.name == "Grade 7").first()
        if cls is not None and cls.status != "completed":
            self.classes.update_class(
                user=actor, class_id=cls.id, name=cls.name, status="completed"
            )

    def seed_payments(self, actor: User) -> None:
        methods = ["cash", "bank", "other"]
        with self.db.session() as session:
            students = (
                session.query(Student)
                .order_by(Student.class_id, Student.id)
                .all()
            )
            monthly_by_class = {
                cls.id: cls.default_template.amount_cents
                for cls in session.query(Class).all()
                if cls.default_template is not None
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
                if profile == "credit" and offset == 0:
                    cents += 5000  # overpay -> the excess becomes account credit
                self.payments.record_payment(
                    user=actor,
                    student_id=student.id,
                    amount=f"{cents / 100:.2f}",
                    method=methods[position % len(methods)],
                    paid_on=_safe_day(self.today, year, month, 3 + position % 3),
                    month=month,
                    year=year,
                )

    def archive_a_student(self, actor: User) -> Student | None:
        """Leave one never-paying student archived but still in arrears."""
        with self.db.session() as session:
            student = (
                session.query(Student)
                .order_by(Student.id)
                .filter(Student.status == "active")
                .first()
            )
        if student is None:
            return None
        self.students.archive_student(user=actor, student_id=student.id)
        return student

    def seed_waiver(self, actor: User, student: Student | None) -> None:
        """Waive the archived student's newest owed month in full (FW-10/FW-11)."""
        if student is None:
            return
        from app.fees.account import expected_cents

        year, month = _recent_periods(self.today)[-1]
        with self.db.session() as session:
            live = session.get(Student, student.id)
            assert live is not None
            closed = {(row.month, row.year) for row in session.query(ClosedMonth).all()}
            amount = expected_cents(session, live, month, year, closed, date.today())
        if amount <= 0:
            return
        self.waivers.add_waiver(
            user=actor,
            student_id=student.id,
            month=month,
            year=year,
            amount=f"{amount / 100:.2f}",
            label="Sponsorship — month covered",
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
            for cat, description, amount, method, day in plan:
                self.expenses.record_expense(
                    user=actor,
                    category_id=category_ids[cat],
                    description=description,
                    amount=amount,
                    method=method,
                    occurred_on=_safe_day(self.today, year, month, day),
                )

    # ------------------------------------------------------------------ report

    def summary(self) -> None:
        from app.arrears.service import ArrearsService

        with self.db.session() as session:
            templates = session.query(FeeTemplate).count()
            students = session.query(Student).count()
            payments = session.query(Payment).count()
            waivers = session.query(Waiver).count()
            expenses = session.query(Expense).count()
            categories = session.query(ExpenseCategory).count()
        arrears_lines = len(ArrearsService(self.db).arrears_report())
        print(
            f"Seeded: {len(TEMPLATES)} templates, "
            f"{len(CLASS_STUDENT_COUNTS)} classes, {students} students, "
            f"{payments} payments, {waivers} waiver(s), "
            f"{categories} expense categories, {expenses} expenses, "
            f"{arrears_lines} student(s) in arrears."
        )


def reset_domain(db: Database) -> None:
    """Delete demo domain data (never users, profile, or audit)."""
    with db.session() as session:
        # Children before parents to satisfy FK constraints (Postgres).
        session.query(Expense).delete()
        session.query(ExpenseCategory).delete()
        session.query(Waiver).delete()
        session.query(Credit).delete()
        session.query(Payment).delete()
        session.query(StudentAmountChange).delete()
        session.query(Student).delete()
        session.query(ClosedMonth).delete()
        session.query(Class).delete()
        session.query(FeeTemplate).delete()
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
    template_ids = seeder.seed_templates(actor)
    seeder.seed_classes_and_students(actor, template_ids)
    seeder.complete_grade7(actor)
    seeder.seed_payments(actor)
    archived = seeder.archive_a_student(actor)
    seeder.seed_waiver(actor, archived)
    seeder.seed_expenses(actor)
    seeder.summary()
    print("Done. Start the app (run.bat) and log in with admin/admin123.")


if __name__ == "__main__":
    main()

"""Schema foundation: tables are created on startup, amounts stay as cents, and
the fee-billing reshape is reflected (no charge rows — enrollment-derived model).
Templates carry a default template per class, an optional linked template per
student, and an ``archived`` flag; amount changes are effective-dated rows in
``student_amount_changes``.
"""

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Campus,
    Class,
    ClosedMonth,
    FeeTemplate,
    Payment,
    School,
    Student,
    StudentAmountChange,
    User,
    UserRoles,
    Waiver,
)

EXPECTED_TABLES = {
    "users",
    "sessions",
    "classes",
    "students",
    "fee_templates",
    "student_amount_changes",
    "waivers",
    "closed_months",
    "payments",
    "credits",
    "expense_categories",
    "expenses",
    "audit_log",
    "school_profile",
    "schools",
    "campuses",
}

# Every operational table is scoped by a nullable ``campus_id`` (MD-2). The
# School is reached via the campus → school join, never a denormalized school_id.
OPERATIONAL_TABLES = {
    "classes",
    "students",
    "fee_templates",
    "student_amount_changes",
    "waivers",
    "closed_months",
    "payments",
    "credits",
    "expense_categories",
    "expenses",
    "audit_log",
}

REMOVED_TABLES = {
    "fee_items",
    "charges",
    "adjustments",
    "payment_allocations",
    "generation_records",
}


def _make_class(db) -> Class:
    with db.session() as session:
        school_class = Class(name="Grade 3")
        session.add(school_class)
        session.commit()
        session.refresh(school_class)
        return school_class


def _make_student(db, session: Session) -> Student:
    school_class = _make_class(db)
    student = Student(class_id=school_class.id, first_name="Ada", last_name="Lovelace")
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def test_create_all_creates_every_domain_table(db):
    tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert REMOVED_TABLES.isdisjoint(tables)


def test_money_is_stored_as_integer_cents(db, session: Session):
    template = FeeTemplate(name="Standard", amount_cents=10000)
    session.add(template)
    session.commit()

    stored = session.query(FeeTemplate).one()
    assert stored.amount_cents == 10000
    assert isinstance(stored.amount_cents, int)


def test_student_defaults_enrolled_today_with_no_archive(db, session: Session):
    student = _make_student(db, session)

    assert student.enrolled_on == date.today()
    assert student.archived_on is None


def test_payment_requires_a_month_and_year_tag(db, session: Session):
    student = _make_student(db, session)

    with pytest.raises(IntegrityError):
        session.add(
            Payment(
                student_id=student.id,
                amount_cents=5000,
                method="cash",
                paid_on=date(2026, 3, 5),
            )
        )
        session.commit()


def test_payment_stores_the_month_tag(db, session: Session):
    student = _make_student(db, session)
    payment = Payment(
        student_id=student.id,
        amount_cents=5000,
        method="cash",
        paid_on=date(2026, 3, 5),
        month=3,
        year=2026,
    )
    session.add(payment)
    session.commit()

    stored = session.query(Payment).one()
    assert (stored.month, stored.year) == (3, 2026)


def test_waiver_allows_stacking_on_the_same_month(db, session: Session):
    student = _make_student(db, session)

    for cents in (2000, 1500):
        session.add(
            Waiver(
                student_id=student.id,
                month=3,
                year=2026,
                amount_cents=cents,
                label="Hardship",
            )
        )
    session.commit()

    assert session.query(Waiver).count() == 2


def test_waiver_allows_stacking_on_different_months(db, session: Session):
    student = _make_student(db, session)
    for month in (3, 4):
        session.add(
            Waiver(
                student_id=student.id,
                month=month,
                year=2026,
                amount_cents=1000,
                label="Hardship",
            )
        )
    session.commit()

    assert session.query(Waiver).count() == 2


def test_closed_month_is_unique_per_month_year(db, session: Session):
    session.add(ClosedMonth(month=7, year=2026))
    session.commit()

    with pytest.raises(IntegrityError):
        session.add(ClosedMonth(month=7, year=2026))
        session.commit()


def test_round_trip_user_and_class(db, session: Session):
    session.add(User(username="admin", name="Head Teacher", password_hash="x", role="admin"))
    session.add(Class(name="Grade 3", status="active"))
    session.commit()

    assert session.query(User).count() == 1
    assert session.query(Class).one().name == "Grade 3"


# ---------------------------------------------------------------------------
# Tenant layer (multi-school ticket 01) — additive only
# ---------------------------------------------------------------------------


def test_user_roles_grow_to_four_values():
    assert {
        UserRoles.SUPERADMIN,
        UserRoles.OWNER,
        UserRoles.ADMIN,
        UserRoles.FINANCE,
    } == {"superadmin", "owner", "admin", "finance"}


def test_campus_has_school_foreign_key_and_profile_shape(db):
    columns = {column["name"] for column in inspect(db.engine).get_columns("campuses")}
    assert {
        "school_id",
        "name",
        "logo_filename",
        "address",
        "phone",
        "email",
        "website",
        "archived",
    } <= columns

    foreign_keys = inspect(db.engine).get_foreign_keys("campuses")
    assert any(
        fk["constrained_columns"] == ["school_id"]
        and fk["referred_table"] == "schools"
        for fk in foreign_keys
    )


def test_campus_archived_is_a_soft_delete_flag(db, session: Session):
    school = School(name="Sunrise Primary")
    session.add(school)
    session.commit()
    session.refresh(school)
    session.add(Campus(school_id=school.id, name="Main Campus"))
    session.commit()

    stored = session.query(Campus).one()
    assert stored.school_id == school.id
    assert stored.school.name == "Sunrise Primary"
    assert stored.archived is False


def test_every_operational_table_has_a_nullable_campus_id(db):
    for table in OPERATIONAL_TABLES:
        columns = {column["name"]: column for column in inspect(db.engine).get_columns(table)}
        assert "campus_id" in columns, f"{table} missing campus_id"
        assert columns["campus_id"]["nullable"] is True, f"{table} campus_id not nullable"
        foreign_keys = inspect(db.engine).get_foreign_keys(table)
        assert any(
            fk["constrained_columns"] == ["campus_id"]
            and fk["referred_table"] == "campuses"
            for fk in foreign_keys
        ), f"{table} campus_id does not reference campuses"


def test_users_carry_nullable_scope_columns(db):
    columns = {column["name"]: column for column in inspect(db.engine).get_columns("users")}
    assert columns["school_id"]["nullable"] is True
    assert columns["campus_id"]["nullable"] is True

    foreign_keys = inspect(db.engine).get_foreign_keys("users")
    assert any(
        fk["constrained_columns"] == ["school_id"] and fk["referred_table"] == "schools"
        for fk in foreign_keys
    )
    assert any(
        fk["constrained_columns"] == ["campus_id"] and fk["referred_table"] == "campuses"
        for fk in foreign_keys
    )


def test_operational_row_round_trips_a_campus(db, session: Session):
    school = School(name="Sunrise Primary")
    session.add(school)
    session.flush()
    campus = Campus(school_id=school.id, name="Main Campus")
    session.add(campus)
    session.flush()

    school_class = Class(name="Grade 3", campus_id=campus.id)
    session.add(school_class)
    session.commit()

    stored = session.query(Class).one()
    assert stored.campus_id == campus.id
    assert stored.campus.school.name == "Sunrise Primary"


# ---------------------------------------------------------------------------
# Fee-template wiring (ticket 02)
# ---------------------------------------------------------------------------


def test_class_default_template_foreign_key(db):
    fks = inspect(db.engine).get_foreign_keys("classes")

    assert any(
        fk["constrained_columns"] == ["default_template_id"]
        and fk["referred_table"] == "fee_templates"
        for fk in fks
    )


def test_student_linked_template_foreign_key(db):
    fks = inspect(db.engine).get_foreign_keys("students")

    assert any(
        fk["constrained_columns"] == ["fee_template_id"]
        and fk["referred_table"] == "fee_templates"
        for fk in fks
    )


def test_fee_template_defaults_to_not_archived(db, session: Session):
    session.add(FeeTemplate(name="Standard", amount_cents=10000))
    session.commit()

    assert session.query(FeeTemplate).one().archived is False


def test_class_default_template_round_trip(db, session: Session):
    template = FeeTemplate(name="Standard", amount_cents=10000)
    session.add(template)
    session.commit()
    session.refresh(template)
    school_class = Class(name="Grade 3", default_template_id=template.id)
    session.add(school_class)
    session.commit()

    stored = session.query(Class).one()
    assert stored.default_template_id == template.id
    assert stored.default_template.name == "Standard"


def test_student_amount_change_stores_an_effective_dated_amount(
    db, session: Session
):
    school_class = _make_class(db)
    template = FeeTemplate(name="Standard", amount_cents=10000)
    session.add(template)
    session.flush()
    student = Student(
        class_id=school_class.id,
        first_name="Ada",
        last_name="Lovelace",
        fee_template_id=template.id,
    )
    session.add(student)
    session.flush()
    session.add(
        StudentAmountChange(student_id=student.id, amount_cents=12000, month=4, year=2026)
    )
    session.commit()

    stored = session.query(StudentAmountChange).one()
    assert stored.student_id == student.id
    assert stored.amount_cents == 12000
    assert (stored.month, stored.year) == (4, 2026)

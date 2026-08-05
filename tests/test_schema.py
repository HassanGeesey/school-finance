"""Schema foundation: tables are created on startup and amounts stay as cents."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import Class, FeeItem, User

EXPECTED_TABLES = {
    "users",
    "sessions",
    "classes",
    "fee_items",
    "students",
    "charges",
    "adjustments",
    "payments",
    "payment_allocations",
    "credits",
    "expenses",
    "expense_categories",
    "audit_log",
    "generation_records",
}


def test_create_all_creates_every_domain_table(db):
    tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_money_is_stored_as_integer_cents(db, session: Session):
    school_class = Class(name="Grade 3")
    session.add(school_class)
    session.flush()
    session.add(FeeItem(class_id=school_class.id, name="Tuition", amount_cents=50000))
    session.commit()

    stored = session.query(FeeItem).one()
    assert stored.amount_cents == 50000
    assert isinstance(stored.amount_cents, int)


def test_round_trip_user_and_class(db, session: Session):
    session.add(User(username="admin", name="Head Teacher", password_hash="x", role="admin"))
    session.add(Class(name="Grade 3", status="active"))
    session.commit()

    assert session.query(User).count() == 1
    assert session.query(Class).one().name == "Grade 3"

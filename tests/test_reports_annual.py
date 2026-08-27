"""Annual Finance Report & School Reports (multi-school ticket 10).

Service-level tests with a seeded scope (two Campuses of one School): the
annual report rolls up income/expenses per month for a calendar year, caps the
arrears figure to the year's owed months, and never leaks the other Campus;
the school-wide rollup computes each Campus side by side and rolls the totals
up. Route concerns follow the two-Campus pattern: Campus-bound staff see only
their own Campus's annual figures, Superadmin/Owner reach the School Reports
hub, the All-Campuses rollup, and the drill-down read-only, and staff never
reach the School surface. All three surfaces export CSV.
"""

from datetime import date

import pytest

from app.arrears.service import ArrearsService
from app.models import (
    Class,
    School,
    Student,
    StudentAmountChange,
    User,
    UserRoles,
)
from app.reports.service import ReportService
from app.schools.service import SchoolDashboardService
from app.tenants.scope import RequestScope, scope_context

from tests.helpers import PASSWORD, authenticated_admin, login_as, seed_second_campus
from tests.test_reports_scope import expense, payment
from tests.test_tenant_scope import seed_tenant_world


@pytest.fixture()
def reports(db) -> ReportService:
    return ReportService(db, arrears=ArrearsService(db))


@pytest.fixture()
def school_service(db, reports) -> SchoolDashboardService:
    return SchoolDashboardService(db, audit=None, reports=reports)


def billed_in(session, class_, campus_id, first, last, year, month=1, amount_cents=10000):
    """A student enrolled at the start of ``year`` with a seeded monthly amount."""
    student = Student(
        class_id=class_.id,
        campus_id=campus_id,
        first_name=first,
        last_name=last,
        enrolled_on=date(year, month, 1),
    )
    session.add(student)
    session.flush()
    session.add(
        StudentAmountChange(
            student_id=student.id,
            campus_id=campus_id,
            amount_cents=amount_cents,
            month=month,
            year=year,
        )
    )
    session.flush()
    return student


def class_for(session, campus, name):
    cls = Class(name=name, campus_id=campus.id)
    session.add(cls)
    session.flush()
    return cls


# ---------------------------------------------------------------------------
# Annual Finance Report — service level
# ---------------------------------------------------------------------------


def test_annual_finance_rolls_up_each_month_for_the_campus(reports, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls = class_for(session, campus_a, "Grade A")
    student = billed_in(session, cls, campus_a.id, "Ada", "Lovelace", 2025)
    payment(session, student, 1, 2025, 10000, paid_on=date(2025, 1, 15))
    payment(session, student, 2, 2025, 5000, paid_on=date(2025, 2, 10))
    expense(session, campus_a.id, "Supplies", 2000, date(2025, 1, 20))
    expense(session, campus_a.id, "Transport", 1000, date(2025, 3, 5))
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        report = reports.annual_finance(2025)

    assert report.year == 2025
    assert len(report.monthly) == 12
    jan, feb, mar = report.monthly[0], report.monthly[1], report.monthly[2]
    assert (jan.month, jan.year) == (1, 2025)
    assert jan.income_cents == 10000
    assert jan.expenses_cents == 2000
    assert jan.net_cents == 8000
    assert feb.income_cents == 5000
    assert feb.expenses_cents == 0
    assert mar.income_cents == 0
    assert mar.expenses_cents == 1000
    assert report.income_cents == 15000
    assert report.expenses_cents == 3000
    assert report.net_cents == 12000
    # A month with no activity is a zero row, never omitted.
    assert report.monthly[11].income_cents == 0
    assert report.monthly[11].expenses_cents == 0


def test_annual_finance_is_campus_scoped(reports, session):
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls_a = class_for(session, campus_a, "Grade A")
    cls_b = class_for(session, campus_b, "Grade B")
    student_a = billed_in(session, cls_a, campus_a.id, "Ada", "Lovelace", 2025)
    student_b = billed_in(session, cls_b, campus_b.id, "Grace", "Hopper", 2025)
    payment(session, student_a, 1, 2025, 10000, paid_on=date(2025, 1, 15))
    payment(session, student_b, 1, 2025, 99999, paid_on=date(2025, 1, 16))
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        report = reports.annual_finance(2025)

    assert report.income_cents == 10000
    assert report.monthly[0].income_cents == 10000


def test_annual_finance_arrears_cap_to_the_years_owed_months(reports, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls = class_for(session, campus_a, "Grade A")
    # Enrolled at the start of 2025 at $100/month and never paid: owes all twelve.
    student = billed_in(session, cls, campus_a.id, "Ada", "Lovelace", 2025)
    # Enrolled after the year end: must not add any 2025 arrears.
    billed_in(session, cls, campus_a.id, "Zoe", "Later", 2026, month=3)
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        report = reports.annual_finance(2025)

    assert report.year_end_arrears_cents == 12 * 10000


def test_annual_finance_school_scope_sees_every_campus(reports, session):
    _school, campus_a, campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)
    cls_a = class_for(session, campus_a, "Grade A")
    cls_b = class_for(session, campus_b, "Grade B")
    student_a = billed_in(session, cls_a, campus_a.id, "Ada", "Lovelace", 2025)
    student_b = billed_in(session, cls_b, campus_b.id, "Grace", "Hopper", 2025)
    payment(session, student_a, 1, 2025, 10000, paid_on=date(2025, 1, 15))
    payment(session, student_b, 3, 2025, 4000, paid_on=date(2025, 3, 15))
    session.commit()

    with scope_context(RequestScope.for_user(superadmin)):
        report = reports.annual_finance(2025)

    assert report.income_cents == 14000
    assert report.monthly[0].income_cents == 10000
    assert report.monthly[2].income_cents == 4000


def test_annual_years_lists_years_with_data_newest_first(reports, session):
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)
    cls = class_for(session, campus_a, "Grade A")
    student = billed_in(session, cls, campus_a.id, "Ada", "Lovelace", 2024)
    payment(session, student, 1, 2024, 1000, paid_on=date(2024, 1, 5))
    expense(session, campus_a.id, "Supplies", 500, date(2026, 4, 2))
    session.commit()

    with scope_context(RequestScope.for_user(admin_a)):
        # The still-active student owes every year from 2024 through today, so
        # 2025 and the current year are in the list too.
        assert reports.annual_years() == [2026, 2025, 2024]


# ---------------------------------------------------------------------------
# Annual rollup — school service level
# ---------------------------------------------------------------------------


def test_annual_rollup_isolates_campuses_and_rolls_totals(school_service, reports, session):
    _school, campus_a, campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)
    cls_a = class_for(session, campus_a, "Grade A")
    cls_b = class_for(session, campus_b, "Grade B")
    student_a = billed_in(session, cls_a, campus_a.id, "Ada", "Lovelace", 2025)
    student_b = billed_in(session, cls_b, campus_b.id, "Grace", "Hopper", 2025)
    payment(session, student_a, 1, 2025, 10000, paid_on=date(2025, 1, 15))
    payment(session, student_b, 3, 2025, 4000, paid_on=date(2025, 3, 15))
    session.commit()

    with scope_context(RequestScope.for_user(superadmin)):
        rollup = school_service.annual_rollup(2025)

    assert {entry.campus.id for entry in rollup.campuses} == {campus_a.id, campus_b.id}
    by_campus = {entry.campus.id: entry.report for entry in rollup.campuses}
    assert by_campus[campus_a.id].income_cents == 10000
    assert by_campus[campus_b.id].income_cents == 4000
    assert rollup.income_cents == 14000
    assert rollup.expenses_cents == 0
    assert rollup.monthly[0].income_cents == 10000
    assert rollup.monthly[2].income_cents == 4000
    assert rollup.monthly[2].net_cents == 4000


def test_annual_rollup_school_annual_years(reports, session):
    _school, campus_a, campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)
    cls_a = class_for(session, campus_a, "Grade A")
    cls_b = class_for(session, campus_b, "Grade B")
    student_a = billed_in(session, cls_a, campus_a.id, "Ada", "Lovelace", 2024)
    student_b = billed_in(session, cls_b, campus_b.id, "Grace", "Hopper", 2026)
    payment(session, student_a, 1, 2024, 1000, paid_on=date(2024, 1, 5))
    payment(session, student_b, 1, 2026, 2000, paid_on=date(2026, 1, 5))
    session.commit()

    with scope_context(RequestScope.for_user(superadmin)):
        # The 2024 student is still active, so 2025 and 2026 are owed years too.
        assert reports.annual_years() == [2026, 2025, 2024]


# ---------------------------------------------------------------------------
# Annual Finance Report — routes
# ---------------------------------------------------------------------------


def test_annual_report_is_campus_scoped_on_the_route(client):
    from tests.test_fee_money_routes import seed_two_campuses
    from tests.test_fee_money_routes import login_as_b
    from tests.test_reports_scope_routes import record_payment

    ids = seed_two_campuses(client)
    today = date.today()
    assert record_payment(client, ids["student_a_id"], "50.00", today).status_code == 303

    page = client.get("/reports/annual")
    assert page.status_code == 200
    assert "Annual finance report" in page.text
    assert "50.00" in page.text

    login_as_b(client)
    page = client.get("/reports/annual")
    assert page.status_code == 200
    assert "50.00" not in page.text


def test_annual_report_csv_is_campus_scoped_on_the_route(client):
    from tests.test_fee_money_routes import seed_two_campuses
    from tests.test_reports_scope_routes import record_payment

    ids = seed_two_campuses(client)
    today = date.today()
    assert record_payment(client, ids["student_a_id"], "50.00", today).status_code == 303

    response = client.get("/reports/annual.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "50.00" in response.text


# ---------------------------------------------------------------------------
# School Reports — routes (Superadmin / Owner)
# ---------------------------------------------------------------------------


def test_campus_staff_never_reach_school_reports(client):
    authenticated_admin(client)

    assert client.get("/school/reports").status_code == 403
    assert client.get("/school/reports/annual").status_code == 403
    assert client.get("/school/reports/annual.csv").status_code == 403


def test_superadmin_school_reports_hub_and_rollup(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    hub = client.get("/school/reports")
    assert hub.status_code == 200
    assert "School Reports" in hub.text
    assert "Annual finance rollup" in hub.text
    assert "Campus B" in hub.text

    rollup = client.get("/school/reports/annual")
    assert rollup.status_code == 200
    assert "Annual finance rollup" in rollup.text
    assert "Campus B" in rollup.text

    csv = client.get("/school/reports/annual.csv")
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    assert "Campus B" in csv.text
    assert "School total" in csv.text


def test_owner_reaches_school_reports_read_only(client):
    from app.auth.service import hash_password
    from app.models import User, UserRoles

    authenticated_admin(client)
    seed_second_campus(client)
    with client.app.state.db.session() as session:
        school = session.query(School).first()
        session.add(
            User(
                name="Board",
                username="board",
                password_hash=hash_password("long enough password"),
                role=UserRoles.OWNER,
                school_id=school.id,
            )
        )
        session.commit()
    login_as(client, "board")

    assert client.get("/school/reports").status_code == 200
    assert client.get("/school/reports/annual").status_code == 200
    assert client.get("/school/reports/annual.csv").status_code == 200


def test_superadmin_drills_into_a_campus_annual_report(client):
    authenticated_admin(client)
    campus_b_id, _superadmin_id = seed_second_campus(client)
    login_as(client, "super")

    page = client.get(f"/campuses/{campus_b_id}/reports/annual")
    assert page.status_code == 200
    assert "Annual finance report" in page.text

    csv = client.get(f"/campuses/{campus_b_id}/reports/annual.csv")
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]

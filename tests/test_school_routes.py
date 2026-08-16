"""School Dashboard routes end-to-end (multi-school ticket 08).

Role-authenticated route tests with two Campuses: the Superadmin (school-bound)
manages Campuses and Owner accounts and browses every Campus read-only; the
Owner browses read-only and is refused every mutation; Campus-bound staff never
see the School Dashboard. The service-level rules live in
``test_school_service.py``.
"""

from typing import cast
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI

from app.auth.service import hash_password
from app.models import AuditLogEntry, Campus, School, User, UserRoles

from tests.helpers import (
    PASSWORD,
    authenticated_admin,
    login,
    login_as,
    seed_second_campus,
    setup_admin,
)
from tests.test_fee_money_routes import seed_two_campuses


def _db(client):
    return cast(FastAPI, client.app).state.db


def campuses(client) -> list[Campus]:
    with _db(client).session() as session:
        return session.query(Campus).order_by(Campus.id).all()


def users(client) -> list[User]:
    with _db(client).session() as session:
        return session.query(User).order_by(User.id).all()


def owners(client) -> list[User]:
    return [u for u in users(client) if u.role == UserRoles.OWNER]


def audit_entries(client, action):
    with _db(client).session() as session:
        return (
            session.query(AuditLogEntry)
            .filter_by(action=action)
            .order_by(AuditLogEntry.id)
            .all()
        )


def add_superadmin(client) -> None:
    """Create a School-bound Superadmin and log in as them (password: superpass)."""
    with _db(client).session() as session:
        school = session.query(School).one()
        session.add(
            User(
                name="Super",
                username="super",
                password_hash=hash_password("superpass"),
                role=UserRoles.SUPERADMIN,
                school_id=school.id,
            )
        )
        session.commit()
    login_as(client, "super", password="superpass")


# ---------------------------------------------------------------------------
# Access & gating
# ---------------------------------------------------------------------------


def test_school_dashboard_requires_login(client):
    setup_admin(client)

    response = client.get("/school", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_campus_staff_do_not_see_the_school_dashboard(client):
    authenticated_admin(client)

    response = client.get("/school", follow_redirects=False)
    assert response.status_code == 403


def test_the_superadmin_home_is_the_school_dashboard(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/school"


# ---------------------------------------------------------------------------
# Superadmin management
# ---------------------------------------------------------------------------


def test_superadmin_creates_a_campus(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    response = client.post(
        "/school/campuses",
        data={"name": "Campus C", "phone": "+1 555"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/school?msg=")
    created = campuses(client)[-1]
    assert created.name == "Campus C"
    assert created.phone == "+1 555"
    (entry,) = audit_entries(client, "campus_create")
    assert entry.campus_id is None  # school-level (MD-2)
    assert "Campus C" in entry.summary


def test_superadmin_creates_a_campus_with_its_admin(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    response = client.post(
        "/school/campuses",
        data={
            "name": "Campus D",
            "admin_name": "Jane Head",
            "admin_username": "jane",
            "admin_password": "temporary password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    admin = [u for u in users(client) if u.username == "jane"][0]
    created = campuses(client)[-1]
    assert admin.role == UserRoles.ADMIN
    assert admin.campus_id == created.id
    assert len(audit_entries(client, "campus_admin_assign")) == 1


def test_superadmin_can_assign_a_campus_admin_later(client):
    authenticated_admin(client)
    _campus_b_id, _super = seed_second_campus(client)
    login_as(client, "super")

    response = client.post(
        f"/school/campuses/{_campus_b_id}/admin",
        data={"name": "Bob B", "username": "bob_b", "password": "temporary password"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    admin = [u for u in users(client) if u.username == "bob_b"][0]
    assert admin.campus_id == _campus_b_id
    assert len(audit_entries(client, "campus_admin_assign")) == 1


def test_superadmin_archives_a_campus(client):
    authenticated_admin(client)
    campus_b_id, _super = seed_second_campus(client)
    login_as(client, "super")

    response = client.post(
        f"/school/campuses/{campus_b_id}/archive", follow_redirects=False
    )

    assert response.status_code == 303
    with _db(client).session() as session:
        assert session.get(Campus, campus_b_id).archived is True
    assert len(audit_entries(client, "campus_archive")) == 1


def test_superadmin_cannot_archive_the_last_active_campus(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    with _db(client).session() as session:
        only_id = (
            session.query(Campus)
            .filter(Campus.archived.is_(False))
            .order_by(Campus.id)
            .first()
        ).id

    # Archive every other active campus, leaving just one.
    with _db(client).session() as session:
        for row in session.query(Campus).filter(Campus.archived.is_(False)).all():
            if row.id != only_id:
                client.post(f"/school/campuses/{row.id}/archive", follow_redirects=False)

    response = client.post(
        f"/school/campuses/{only_id}/archive", follow_redirects=False
    )
    assert response.status_code == 303
    err = parse_qs(urlparse(response.headers["location"]).query).get("err", [""])[0]
    assert "only active Campus" in err


def test_superadmin_creates_and_manages_an_owner(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    response = client.post(
        "/school/owners",
        data={"name": "The Board", "username": "board", "password": "temporary password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    (owner,) = owners(client)
    assert owner.username == "board"
    assert owner.school_id is not None
    assert owner.campus_id is None
    assert len(audit_entries(client, "owner_create")) == 1

    response = client.post(f"/school/owners/{owner.id}/disable", follow_redirects=False)
    assert response.status_code == 303
    assert not [u for u in users(client) if u.id == owner.id][0].is_active
    assert len(audit_entries(client, "owner_disable")) == 1

    response = client.post(f"/school/owners/{owner.id}/enable", follow_redirects=False)
    assert response.status_code == 303
    assert [u for u in users(client) if u.id == owner.id][0].is_active is True
    assert len(audit_entries(client, "owner_enable")) == 1


def test_superadmin_sees_every_campus_on_the_dashboard(client):
    authenticated_admin(client)
    _campus_b_id, _super = seed_second_campus(client)
    login_as(client, "super")

    page = client.get("/school")

    assert page.status_code == 200
    assert "Campus B" in page.text


# ---------------------------------------------------------------------------
# Owner read-only
# ---------------------------------------------------------------------------


def _owner_client(client) -> int:
    """Create a School-bound Owner and log in as them; returns campus_b's id."""
    authenticated_admin(client)
    campus_b_id, _super = seed_second_campus(client)
    with _db(client).session() as session:
        school = session.query(School).one()
        owner = User(
            name="Owner",
            username="owner",
            password_hash=hash_password("long enough password"),
            role=UserRoles.OWNER,
            school_id=school.id,
        )
        session.add(owner)
        session.commit()
    login_as(client, "owner")
    return campus_b_id


def test_owner_sees_the_school_dashboard_read_only(client):
    _owner_client(client)

    page = client.get("/school")

    assert page.status_code == 200
    assert "Read-only view" in page.text
    # No management surface for Owners.
    assert "Add owner" not in page.text
    assert "New campus" not in page.text


def test_owner_cannot_manage_campuses_or_owners(client):
    campus_b_id = _owner_client(client)

    response = client.post(
        "/school/campuses", data={"name": "Campus C"}, follow_redirects=False
    )
    assert response.status_code == 403

    response = client.post(
        f"/school/campuses/{campus_b_id}/archive", follow_redirects=False
    )
    assert response.status_code == 403

    response = client.post(
        "/school/owners", data={"name": "X", "username": "x", "password": "p"}, follow_redirects=False
    )
    assert response.status_code == 403


def test_owner_cannot_mutate_campus_data(client):
    seed_two_campuses(client)
    with _db(client).session() as session:
        school = session.query(School).one()
        owner = User(
            name="Owner",
            username="owner",
            password_hash=hash_password("long enough password"),
            role=UserRoles.OWNER,
            school_id=school.id,
        )
        session.add(owner)
        session.commit()
    login_as(client, "owner")

    # Creating a class (any operational mutation) is refused for school-bound accounts.
    response = client.post(
        "/classes", data={"name": "Grade A", "status": "active"}, follow_redirects=False
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Read-only drill-down
# ---------------------------------------------------------------------------


def test_superadmin_browses_a_campus_read_only(client):
    ids = seed_two_campuses(client)
    add_superadmin(client)

    page = client.get(f"/campuses/{ids['campus_b_id']}")

    assert page.status_code == 200
    assert "Quick actions" not in page.text  # read-only: no record buttons
    assert "Ada Lovelace" not in page.text  # other campus's student stays hidden

    # The campus name shows through the viewed Campus's branding.
    assert "Campus B" in page.text


def test_superadmin_browses_a_campus_students_and_accounts(client):
    ids = seed_two_campuses(client)
    add_superadmin(client)

    page = client.get(f"/campuses/{ids['campus_b_id']}/students")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "Ada Lovelace" not in page.text

    page = client.get(f"/campuses/{ids['campus_b_id']}/students/{ids['student_b_id']}/account")
    assert page.status_code == 200

    # A student from another campus is not reachable through this campus.
    response = client.get(f"/campuses/{ids['campus_b_id']}/students/{ids['student_a_id']}/account")
    assert response.status_code == 404


def test_superadmin_browses_a_campus_classes_fees_payments(client):
    ids = seed_two_campuses(client)
    add_superadmin(client)

    page = client.get(f"/campuses/{ids['campus_b_id']}/classes")
    assert page.status_code == 200
    assert "Grade B" in page.text
    assert "Grade A" not in page.text

    page = client.get(f"/campuses/{ids['campus_b_id']}/fees")
    assert page.status_code == 200
    assert "Standard B" in page.text

    page = client.get(f"/campuses/{ids['campus_b_id']}/payments?q=hopper")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "Ada Lovelace" not in page.text


def test_superadmin_browses_a_campus_reports(client):
    ids = seed_two_campuses(client)
    add_superadmin(client)

    page = client.get(f"/campuses/{ids['campus_b_id']}/reports")
    assert page.status_code == 200
    assert "Income vs Expense" in page.text

    page = client.get(f"/campuses/{ids['campus_b_id']}/reports/students")
    assert page.status_code == 200
    assert "Grace Hopper" in page.text
    assert "Ada Lovelace" not in page.text


def test_an_unknown_campus_is_404(client):
    authenticated_admin(client)
    seed_second_campus(client)
    login_as(client, "super")

    assert client.get("/campuses/999").status_code == 404
    assert client.get("/campuses/999/students").status_code == 404


def test_campus_bound_admin_cannot_use_the_drill_down(client):
    authenticated_admin(client)

    response = client.get("/campuses/1", follow_redirects=False)
    assert response.status_code == 403

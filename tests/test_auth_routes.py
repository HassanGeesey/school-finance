"""Auth routes end-to-end: setup wizard, login/out, session gate, role gate.

Route-level smoke tests of the thin adapters + middleware + templates. Business
rules themselves are covered in ``test_auth_service.py``.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.service import hash_password, verify_password
from app.config import settings
from app.main import create_app
from app.models import User, UserRoles

NAME = "Head Teacher"
USERNAME = "admin"
PASSWORD = "correct horse battery staple"


@pytest.fixture()
def client():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        yield client


def _setup_admin(client) -> None:
    response = client.post(
        "/setup",
        data={"name": NAME, "username": USERNAME, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def _login_admin(client) -> None:
    response = client.post(
        "/login",
        data={"username": USERNAME, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert settings.SESSION_COOKIE in response.headers["set-cookie"]


def _authenticated_admin(client) -> None:
    _setup_admin(client)
    _login_admin(client)


def test_fresh_install_redirects_to_setup_wizard(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")

    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"

    response = client.get("/setup")
    assert response.status_code == 200
    assert "Create admin account" in response.text


def test_setup_creates_admin_then_requires_login(client):
    _setup_admin(client)

    with client.app.state.db.session() as session:
        stored = session.query(User).one()
        assert stored.username == USERNAME
        assert stored.role == UserRoles.ADMIN
        assert stored.password_hash != PASSWORD
        assert verify_password(PASSWORD, stored.password_hash) is True

    # After setup, the app requires login: no session cookie is set.
    _login_admin(client)


def test_setup_rejects_missing_fields(client):
    response = client.post("/setup", data={"name": NAME, "username": "", "password": PASSWORD})
    assert response.status_code == 400
    assert "required" in response.text
    assert response.headers.get("set-cookie") is None


def test_login_and_logout_round_trip(client):
    _authenticated_admin(client)

    response = client.get("/")
    assert response.status_code == 200
    assert NAME in response.text
    assert "Admin" in response.text

    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert "session" in response.headers.get("set-cookie", "")

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303


def test_login_rejects_wrong_password(client):
    _setup_admin(client)

    response = client.post(
        "/login",
        data={"username": USERNAME, "password": "wrong password"},
    )
    assert response.status_code == 400
    assert "Invalid username or password" in response.text
    assert response.headers.get("set-cookie") is None


def test_login_page_redirects_authenticated_users(client):
    _authenticated_admin(client)

    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_honors_a_safe_next_target(client):
    _setup_admin(client)

    response = client.post(
        "/login",
        data={"username": USERNAME, "password": PASSWORD, "next": "/admin"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/admin"


def test_login_ignores_external_next_targets(client):
    _setup_admin(client)

    response = client.post(
        "/login",
        data={"username": USERNAME, "password": PASSWORD, "next": "https://evil.example"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_all_pages_require_a_session(client):
    _setup_admin(client)

    for path in ["/", "/admin"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login"), path


def test_admin_can_open_admin_pages(client):
    _authenticated_admin(client)

    response = client.get("/admin")
    assert response.status_code == 200
    assert "Configuration" in response.text


def test_finance_officer_is_blocked_from_admin_pages(client):
    _authenticated_admin(client)
    with client.app.state.db.session() as session:
        session.add(
            User(
                name="Cashier",
                username="cashier",
                password_hash=hash_password("long enough password"),
                role=UserRoles.FINANCE,
            )
        )
        session.commit()
    client.post("/logout")
    client.post("/login", data={"username": "cashier", "password": "long enough password"})

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 403

    response = client.get("/")
    assert response.status_code == 200
    assert "Cashier" in response.text
    assert "Finance officer" in response.text

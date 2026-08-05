"""App boot smoke tests: the factory serves a styled home page and creates schema."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db import make_engine
from app.main import create_app
from tests.helpers import authenticated_admin, setup_admin


def test_home_requires_login_and_redirects_on_fresh_install():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_static_assets_are_served_locally():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        css = client.get("/static/css/app.css")
        htmx = client.get("/static/js/htmx.min.js")
        chart = client.get("/static/js/chart.umd.min.js")
    assert css.status_code == 200
    assert htmx.status_code == 200
    assert chart.status_code == 200


def test_startup_creates_schema():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        client.get("/")
        tables = set(inspect(app.state.db.engine).get_table_names())
    assert "users" in tables
    assert "charges" in tables


def test_authenticated_pages_use_the_design_system_shell():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        authenticated_admin(client)
        response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "app-sidebar" in html
    assert "School" in html
    assert "Finance" in html
    assert "Fee generation" in html
    assert 'href="/classes"' in html
    assert 'href="/students"' in html
    assert 'href="/fees"' in html
    assert 'href="/audit"' in html
    assert "Head Teacher" in html
    assert "Admin" in html
    assert 'action="/logout"' in html
    assert "confirm-dialog" in html
    assert "toast-container" in html


def test_login_page_is_standalone_without_the_shell():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        setup_admin(client)
        response = client.get("/login")
    assert response.status_code == 200
    html = response.text
    assert "Log in" in html
    assert "app-sidebar" not in html
    assert "sidebar-toggle" not in html
    assert 'action="/logout"' not in html

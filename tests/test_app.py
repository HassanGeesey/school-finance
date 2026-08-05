"""App boot smoke tests: the factory serves a styled home page and creates schema."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db import make_engine
from app.main import create_app


def test_home_page_served():
    app = create_app(database_url="sqlite://")
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "School Finance" in response.text


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

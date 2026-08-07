"""Shared helpers for route-level smoke tests.

The setup/login flows are identical across feature route tests; keeping them in
one place stops each feature module from duplicating them.
"""

from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.service import hash_password
from app.models import User, UserRoles

NAME = "Head Teacher"
USERNAME = "admin"
PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"


def setup_admin(client: TestClient) -> None:
    response = client.post(
        "/setup",
        data={
            "school_name": SCHOOL_NAME,
            "name": NAME,
            "username": USERNAME,
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def login(client: TestClient, username: str = USERNAME, password: str = PASSWORD) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def authenticated_admin(client: TestClient) -> None:
    setup_admin(client)
    login(client)


def add_finance_user(client: TestClient) -> None:
    with cast(FastAPI, client.app).state.db.session() as session:
        session.add(
            User(
                name="Cashier",
                username="cashier",
                password_hash=hash_password("long enough password"),
                role=UserRoles.FINANCE,
            )
        )
        session.commit()


def login_finance(client: TestClient) -> None:
    client.post("/logout", follow_redirects=False)
    login(client, username="cashier", password="long enough password")

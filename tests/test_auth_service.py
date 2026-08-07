"""Auth service: password hashing, first-admin setup, and server-side sessions.

Business rules only — the single testing seam. No route/template concerns here.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.service import (
    AuthError,
    AuthService,
    SetupNotAvailable,
    hash_password,
    safe_post_login_target,
    verify_password,
)
from app.models import AuthSession, SchoolProfile, User, UserRoles
from app.profile.service import ProfileService

PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"


@pytest.fixture()
def auth(db) -> AuthService:
    return AuthService(db, profile=ProfileService(db))


def test_fresh_database_has_no_users(auth):
    assert auth.has_users() is False


def test_setup_first_admin_creates_admin_with_hashed_password(auth, session):
    user = auth.setup_first_admin(name="Head Teacher", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    assert auth.has_users() is True
    stored = session.query(User).one()
    assert stored.id == user.id
    assert stored.name == "Head Teacher"
    assert stored.username == "admin"
    assert stored.role == UserRoles.ADMIN
    assert stored.is_active is True
    assert stored.password_hash != PASSWORD
    assert stored.password_hash.startswith("pbkdf2_sha256$")
    assert verify_password(PASSWORD, stored.password_hash) is True
    assert verify_password("wrong password", stored.password_hash) is False


def test_setup_first_admin_rejects_a_second_admin(auth, session):
    auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    with pytest.raises(SetupNotAvailable):
        auth.setup_first_admin(name="B", username="admin2", password=PASSWORD, school_name=SCHOOL_NAME)
    assert session.query(User).count() == 1


def test_setup_first_admin_requires_name_and_username(auth):
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="   ", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="A", username="", password=PASSWORD, school_name=SCHOOL_NAME)


def test_setup_first_admin_requires_a_password(auth):
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="A", username="admin", password="", school_name=SCHOOL_NAME)


def test_setup_first_admin_requires_a_school_name(auth):
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="A", username="admin", password=PASSWORD)
    with pytest.raises(AuthError):
        auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name="   ")


def test_setup_first_admin_creates_the_school_profile(auth, session):
    auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    profile = session.query(SchoolProfile).one()
    assert profile.id == 1
    assert profile.school_name == SCHOOL_NAME


def test_authenticate_returns_the_user_for_valid_credentials(auth):
    auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    user = auth.authenticate("admin", PASSWORD)
    assert user is not None
    assert user.username == "admin"
    assert user.role == UserRoles.ADMIN


def test_authenticate_rejects_wrong_password_and_unknown_username(auth):
    auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    assert auth.authenticate("admin", "wrong password") is None
    assert auth.authenticate("nobody", PASSWORD) is None


def test_authenticate_rejects_a_disabled_user(auth, session):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    session.query(User).filter(User.id == user.id).update({"is_active": False})
    session.commit()

    assert auth.authenticate("admin", PASSWORD) is None


def test_hash_password_is_salted_and_verifiable():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


def test_verify_password_rejects_malformed_stored_hashes():
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", "md5$1$aa$bb") is False
    assert verify_password("anything", "") is False


def test_create_session_returns_a_token_resolvable_to_the_user(auth):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    token = auth.create_session(user)
    resolved = auth.user_for_token(token)
    assert resolved is not None
    assert resolved.id == user.id
    assert resolved.role == UserRoles.ADMIN


def test_sessions_are_unique_per_login(auth):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)

    token1 = auth.create_session(user)
    token2 = auth.create_session(user)
    assert token1 != token2
    assert auth.user_for_token(token1).id == user.id
    assert auth.user_for_token(token2).id == user.id


def test_user_for_token_rejects_unknown_or_empty_tokens(auth):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    auth.create_session(user)

    assert auth.user_for_token("garbage-token") is None
    assert auth.user_for_token("") is None
    assert auth.user_for_token(None) is None


def test_destroy_session_invalidates_the_token(auth):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    token = auth.create_session(user)
    assert auth.user_for_token(token) is not None

    auth.destroy_session(token)
    assert auth.user_for_token(token) is None


def test_expired_session_is_rejected(auth, session):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    token = auth.create_session(user)
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    session.query(AuthSession).update({"expires_at": past})
    session.commit()

    assert auth.user_for_token(token) is None


def test_user_for_token_rejects_a_session_for_a_disabled_user(auth, session):
    user = auth.setup_first_admin(name="A", username="admin", password=PASSWORD, school_name=SCHOOL_NAME)
    token = auth.create_session(user)
    session.query(User).filter(User.id == user.id).update({"is_active": False})
    session.commit()

    assert auth.user_for_token(token) is None


def test_safe_post_login_target_only_accepts_local_paths():
    assert safe_post_login_target("/admin") == "/admin"
    assert safe_post_login_target("/") == "/"
    assert safe_post_login_target("https://evil.example") == "/"
    assert safe_post_login_target("//evil.example") == "/"
    assert safe_post_login_target("") == "/"

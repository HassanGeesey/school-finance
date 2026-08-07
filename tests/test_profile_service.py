"""Profile service: the school's identity record, its editor, and logos.

Business rules only — the single testing seam. ``LogoStorage`` mechanics are
tested against ``tmp_path``; ``ProfileService`` wires storage to the database
and the audit log. Routes live in ``test_profile_routes.py``.
"""

from __future__ import annotations

import pytest

from app.audit.service import AuditActions, AuditService
from app.models import AuditLogEntry, SchoolProfile, User, UserRoles
from app.profile.service import LogoError, LogoStorage, ProfileError, ProfileService

PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"
GIF_MAGIC = b"GIF89a"
WEBP_MAGIC = b"RIFF\x10\x00\x00\x00WEBPVP8 "
SVG_DATA = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


def _user(session) -> User:
    user = session.query(User).filter_by(username="admin").first()
    if user is None:
        user = User(
            name="Head Teacher",
            username="admin",
            password_hash=PASSWORD,
            role=UserRoles.ADMIN,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def audit_actions(session, action: str) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=action)
        .order_by(AuditLogEntry.id)
        .all()
    )


def make_profile(db, tmp_path) -> ProfileService:
    return ProfileService(db, audit=AuditService(db), logos=LogoStorage(tmp_path))


# ---------------------------------------------------------------------------
# LogoStorage — file mechanics
# ---------------------------------------------------------------------------


def test_logo_storage_saves_an_image_with_a_safe_name(tmp_path):
    storage = LogoStorage(tmp_path)

    filename = storage.save(PNG_MAGIC + b"payload", source_name="school-logo.png")

    assert filename == "logo.png"
    assert (tmp_path / "logo.png").read_bytes() == PNG_MAGIC + b"payload"


def test_logo_storage_rejects_non_image_extensions(tmp_path):
    storage = LogoStorage(tmp_path)

    with pytest.raises(LogoError):
        storage.save(b"x", source_name="evil.exe")
    with pytest.raises(LogoError):
        storage.save(b"x", source_name="logo")


def test_logo_storage_rejects_a_file_renamed_to_an_image(tmp_path):
    storage = LogoStorage(tmp_path)

    with pytest.raises(LogoError):
        storage.save(b"not really a png", source_name="report.png")
    with pytest.raises(LogoError):
        storage.save(b"\xff\xd8\xff", source_name="logo.png")  # JPEG magic, PNG name
    assert not (tmp_path / "logo.png").exists()


def test_logo_storage_accepts_the_image_allowlist(tmp_path):
    storage = LogoStorage(tmp_path)

    assert storage.save(PNG_MAGIC, source_name="x.png") == "logo.png"
    assert storage.save(SVG_DATA, source_name="x.svg") == "logo.svg"
    assert storage.save(JPEG_MAGIC, source_name="x.jpeg") == "logo.jpeg"
    assert storage.save(GIF_MAGIC, source_name="x.gif") == "logo.gif"
    assert storage.save(WEBP_MAGIC, source_name="x.webp") == "logo.webp"


def test_logo_storage_remove_deletes_the_file(tmp_path):
    storage = LogoStorage(tmp_path)
    filename = storage.save(PNG_MAGIC + b"bytes", source_name="x.png")

    storage.remove(filename)

    assert not (tmp_path / filename).exists()
    storage.remove(filename)  # idempotent


def test_logo_storage_media_type_maps_extensions(tmp_path):
    storage = LogoStorage(tmp_path)

    assert storage.media_type("logo.png") == "image/png"
    assert storage.media_type("logo.jpeg") == "image/jpeg"
    assert storage.media_type("logo.svg") == "image/svg+xml"
    assert storage.media_type("logo.unknown") == "application/octet-stream"


# ---------------------------------------------------------------------------
# ProfileService — the single-row record
# ---------------------------------------------------------------------------


def test_get_profile_creates_the_singleton_row(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    profile = service.get_profile()

    assert profile.id == 1
    assert session.query(SchoolProfile).count() == 1
    assert service.get_profile().id == 1
    assert session.query(SchoolProfile).count() == 1


def test_update_profile_saves_fields_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    profile = service.update_profile(
        user=_user(session),
        school_name=SCHOOL_NAME,
        address="123 Main St",
        phone="555-1234",
        email="info@school.example",
        website="https://school.example",
    )

    assert profile.school_name == SCHOOL_NAME
    assert profile.address == "123 Main St"
    assert profile.phone == "555-1234"
    assert profile.email == "info@school.example"
    assert profile.website == "https://school.example"
    (entry,) = audit_actions(session, AuditActions.PROFILE_UPDATE)
    assert "Sunrise Primary School" in entry.summary


def test_update_profile_strips_blank_contact_fields(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    profile = service.update_profile(
        user=None, school_name=SCHOOL_NAME, address="  ", phone=""
    )

    assert profile.address is None
    assert profile.phone is None


def test_update_profile_refuses_a_blank_school_name(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    with pytest.raises(ProfileError):
        service.update_profile(user=_user(session), school_name="   ")

    assert audit_actions(session, AuditActions.PROFILE_UPDATE) == []


def test_update_profile_audits_only_what_changed(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    service.update_profile(
        user=_user(session), school_name=SCHOOL_NAME, address="123 Main St"
    )

    service.update_profile(
        user=_user(session), school_name=SCHOOL_NAME, address="123 Main St"
    )

    assert len(audit_actions(session, AuditActions.PROFILE_UPDATE)) == 1

    service.update_profile(user=_user(session), school_name=SCHOOL_NAME, phone="555-1234")

    (entry,) = audit_actions(session, AuditActions.PROFILE_UPDATE)[1:]
    assert "school name" not in entry.summary
    assert "phone" in entry.summary


# ---------------------------------------------------------------------------
# ProfileService — logo upload & removal
# ---------------------------------------------------------------------------


def test_save_logo_stores_the_file_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    filename = service.save_logo(user=_user(session), data=PNG_MAGIC + b"bytes", source_name="logo.png")

    assert filename == "logo.png"
    assert (tmp_path / "logo.png").exists()
    assert service.get_profile().logo_filename == "logo.png"
    (entry,) = audit_actions(session, AuditActions.PROFILE_LOGO_UPLOAD)
    assert "logo" in entry.summary.lower()


def test_save_logo_replaces_a_previous_logo(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    service.save_logo(user=_user(session), data=PNG_MAGIC, source_name="a.png")

    service.save_logo(user=_user(session), data=SVG_DATA, source_name="b.svg")

    assert (tmp_path / "logo.svg").exists()
    assert not (tmp_path / "logo.png").exists()
    assert service.get_profile().logo_filename == "logo.svg"


def test_save_logo_rejects_a_non_image_without_audit(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    with pytest.raises(LogoError):
        service.save_logo(user=_user(session), data=b"x", source_name="evil.exe")

    assert audit_actions(session, AuditActions.PROFILE_LOGO_UPLOAD) == []


def test_remove_logo_deletes_the_file_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    service.save_logo(user=_user(session), data=PNG_MAGIC + b"bytes", source_name="logo.png")

    service.remove_logo(user=_user(session))

    assert service.get_profile().logo_filename is None
    assert not (tmp_path / "logo.png").exists()
    (entry,) = audit_actions(session, AuditActions.PROFILE_LOGO_REMOVE)
    assert "logo" in entry.summary.lower()


def test_logo_path_follows_the_current_profile(db, session, tmp_path):
    service = make_profile(db, tmp_path)

    assert service.logo_path() is None

    service.save_logo(user=_user(session), data=PNG_MAGIC + b"bytes", source_name="logo.png")

    assert service.logo_path() == tmp_path / "logo.png"


def test_logo_operations_unavailable_without_storage(db, session):
    service = ProfileService(db, audit=AuditService(db))

    with pytest.raises(LogoError):
        service.save_logo(user=None, data=b"x", source_name="logo.png")
    with pytest.raises(LogoError):
        service.remove_logo(user=None)

    assert service.logo_path() is None

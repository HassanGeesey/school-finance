"""Campus profile service: the acting Campus's identity, its editor, and logos.

Business rules only — the single testing seam. ``LogoStorage`` mechanics are
tested against ``tmp_path``; ``ProfileService`` resolves the Campus from the
request scope (Campus-bound roles edit exactly their own Campus) and wires
storage to the database and the audit log. Routes live in
``test_profile_routes.py``.
"""

from __future__ import annotations

import pytest

from app.audit.service import AuditActions, AuditService
from app.models import AuditLogEntry, User
from app.profile.service import LogoError, LogoStorage, ProfileError, ProfileService
from app.tenants.scope import RequestScope, scope_context
from tests.test_tenant_scope import seed_tenant_world

PASSWORD = "correct horse battery staple"
SCHOOL_NAME = "Sunrise Primary School"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"
GIF_MAGIC = b"GIF89a"
WEBP_MAGIC = b"RIFF\x10\x00\x00\x00WEBPVP8 "
SVG_DATA = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


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
# ProfileService — resolving the acting Campus
# ---------------------------------------------------------------------------


def test_get_profile_resolves_the_acting_scope(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        assert service.get_profile().id == campus_a.id
    with scope_context(RequestScope.for_user(admin_b)):
        assert service.get_profile().id == campus_b.id


def test_get_profile_is_none_for_a_school_bound_or_unscoped_call(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, _admin_a, _admin_b, superadmin = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(superadmin)):
        assert service.get_profile() is None
    assert service.get_profile() is None


def test_get_profile_accepts_an_explicit_campus(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, _admin_a, _admin_b, _sa = seed_tenant_world(session)

    assert service.get_profile(campus=campus_a).id == campus_a.id


# ---------------------------------------------------------------------------
# ProfileService — editing the identity
# ---------------------------------------------------------------------------


def test_update_profile_saves_fields_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        profile = service.update_profile(
            user=admin_a,
            school_name=SCHOOL_NAME,
            address="123 Main St",
            phone="555-1234",
            email="info@school.example",
            website="https://school.example",
        )

    assert profile.id == campus_a.id
    assert profile.name == SCHOOL_NAME
    assert profile.address == "123 Main St"
    assert profile.phone == "555-1234"
    assert profile.email == "info@school.example"
    assert profile.website == "https://school.example"
    (entry,) = audit_actions(session, AuditActions.PROFILE_UPDATE)
    assert "Sunrise Primary School" in entry.summary


def test_update_profile_strips_blank_contact_fields(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        profile = service.update_profile(
            user=admin_a, school_name=SCHOOL_NAME, address="  ", phone=""
        )

    assert profile.address is None
    assert profile.phone is None


def test_update_profile_refuses_a_blank_school_name(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(ProfileError):
            service.update_profile(user=admin_a, school_name="   ")

    assert audit_actions(session, AuditActions.PROFILE_UPDATE) == []


def test_update_profile_audits_only_what_changed(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        service.update_profile(
            user=admin_a, school_name=SCHOOL_NAME, address="123 Main St"
        )
        service.update_profile(
            user=admin_a, school_name=SCHOOL_NAME, address="123 Main St"
        )
        assert len(audit_actions(session, AuditActions.PROFILE_UPDATE)) == 1

        service.update_profile(user=admin_a, school_name=SCHOOL_NAME, phone="555-1234")

    (entry,) = audit_actions(session, AuditActions.PROFILE_UPDATE)[1:]
    assert "school name" not in entry.summary
    assert "phone" in entry.summary


def test_a_campus_admin_edits_only_their_own_campus(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, campus_b, admin_a, admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        service.update_profile(
            user=admin_a, school_name="Campus A Academy", phone="111-1111"
        )
    with scope_context(RequestScope.for_user(admin_b)):
        service.update_profile(
            user=admin_b, school_name="Campus B Academy", phone="222-2222"
        )

    session.refresh(campus_a)
    session.refresh(campus_b)
    assert campus_a.name == "Campus A Academy"
    assert campus_a.phone == "111-1111"
    assert campus_b.name == "Campus B Academy"
    assert campus_b.phone == "222-2222"


def test_update_profile_accepts_an_explicit_campus(db, session, tmp_path):
    """The setup wizard passes its implicit Campus explicitly (no scope)."""
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    profile = service.update_profile(
        user=admin_a, campus=campus_a, school_name=SCHOOL_NAME
    )

    assert profile.name == SCHOOL_NAME


def test_update_profile_needs_a_campus_scope(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, _admin_a, _admin_b, _sa = seed_tenant_world(session)

    with pytest.raises(ProfileError):
        service.update_profile(user=None, school_name=SCHOOL_NAME)


# ---------------------------------------------------------------------------
# ProfileService — logo upload & removal
# ---------------------------------------------------------------------------


def test_save_logo_stores_the_file_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        filename = service.save_logo(
            user=admin_a, data=PNG_MAGIC + b"bytes", source_name="logo.png"
        )

    assert filename == "logo.png"
    assert (tmp_path / "logo.png").exists()
    session.refresh(campus_a)
    assert campus_a.logo_filename == "logo.png"
    (entry,) = audit_actions(session, AuditActions.PROFILE_LOGO_UPLOAD)
    assert "logo" in entry.summary.lower()


def test_save_logo_replaces_a_previous_logo(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        service.save_logo(user=admin_a, data=PNG_MAGIC, source_name="a.png")
        service.save_logo(user=admin_a, data=SVG_DATA, source_name="b.svg")

    assert (tmp_path / "logo.svg").exists()
    assert not (tmp_path / "logo.png").exists()
    session.refresh(campus_a)
    assert campus_a.logo_filename == "logo.svg"


def test_save_logo_rejects_a_non_image_without_audit(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(LogoError):
            service.save_logo(user=admin_a, data=b"x", source_name="evil.exe")

    assert audit_actions(session, AuditActions.PROFILE_LOGO_UPLOAD) == []


def test_remove_logo_deletes_the_file_and_audits(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        service.save_logo(user=admin_a, data=PNG_MAGIC + b"bytes", source_name="logo.png")
        service.remove_logo(user=admin_a)

    session.refresh(campus_a)
    assert campus_a.logo_filename is None
    assert not (tmp_path / "logo.png").exists()
    (entry,) = audit_actions(session, AuditActions.PROFILE_LOGO_REMOVE)
    assert "logo" in entry.summary.lower()


def test_logo_path_follows_the_acting_campus(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        assert service.logo_path() is None
        service.save_logo(user=admin_a, data=PNG_MAGIC + b"bytes", source_name="logo.png")
        assert service.logo_path() == tmp_path / "logo.png"


def test_logo_isolation_between_campuses(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, campus_a, campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        service.save_logo(user=admin_a, data=PNG_MAGIC + b"bytes", source_name="logo.png")

    session.refresh(campus_a)
    session.refresh(campus_b)
    assert campus_a.logo_filename == "logo.png"
    assert campus_b.logo_filename is None


def test_logo_operations_require_a_campus_scope(db, session, tmp_path):
    service = make_profile(db, tmp_path)
    _school, _campus_a, _campus_b, _admin_a, _admin_b, _sa = seed_tenant_world(session)

    with pytest.raises(LogoError):
        service.save_logo(user=None, data=PNG_MAGIC, source_name="logo.png")
    with pytest.raises(LogoError):
        service.remove_logo(user=None)


def test_logo_operations_unavailable_without_storage(db, session):
    service = ProfileService(db, audit=AuditService(db))
    _school, _campus_a, _campus_b, admin_a, _admin_b, _sa = seed_tenant_world(session)

    with scope_context(RequestScope.for_user(admin_a)):
        with pytest.raises(LogoError):
            service.save_logo(user=admin_a, data=b"x", source_name="logo.png")
        with pytest.raises(LogoError):
            service.remove_logo(user=admin_a)
        assert service.logo_path() is None
        assert service.logo_media_type() == "application/octet-stream"


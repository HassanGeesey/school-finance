"""System service: backups and shutdown.

Backups business rules (file copy, rotation, list ordering) live in
``BackupService`` and are tested against ``tmp_path`` — no database needed.
``SystemService`` wires the backup service to the audit log and handles the
in-app shutdown request. Routes are thin adapters in ``test_system_routes.py``.
"""

from __future__ import annotations

import time

import pytest

from app.audit.service import AuditActions, AuditService
from app.models import AuditLogEntry, User, UserRoles
from app.system.service import (
    BACKUP_FILENAME_PREFIX,
    BackupError,
    BackupService,
    SystemService,
)

PASSWORD = "correct horse battery staple"


def _user(session) -> User:
    user = User(name="Head Teacher", username="admin", password_hash="x", role=UserRoles.ADMIN)
    session.add(user)
    session.commit()
    return user


def audit_actions(session, action: str) -> list[AuditLogEntry]:
    return (
        session.query(AuditLogEntry)
        .filter_by(action=action)
        .order_by(AuditLogEntry.id)
        .all()
    )


# ---------------------------------------------------------------------------
# BackupService — file mechanics
# ---------------------------------------------------------------------------


def make_backup_service(tmp_path, keep=3):
    source = tmp_path / "school_finance.db"
    source.write_bytes(b"sqlite-bytes")
    backup_dir = tmp_path / "backups"
    return BackupService(source_path=source, backup_dir=backup_dir, keep=keep), source, backup_dir


def test_create_backup_copies_the_database_file(tmp_path):
    service, _source, backup_dir = make_backup_service(tmp_path)

    created = service.create_backup()

    assert created.exists()
    assert created.read_bytes() == b"sqlite-bytes"
    assert created.name.startswith(BACKUP_FILENAME_PREFIX)
    assert created.parent == backup_dir


def test_create_backup_creates_the_backup_directory(tmp_path):
    service, _source, backup_dir = make_backup_service(tmp_path)

    service.create_backup()

    assert backup_dir.is_dir()


def test_create_backup_fails_clearly_when_the_source_is_missing(tmp_path):
    service = BackupService(
        source_path=tmp_path / "missing.db",
        backup_dir=tmp_path / "backups",
        keep=3,
    )

    with pytest.raises(BackupError):
        service.create_backup()


def test_each_backup_gets_a_unique_timestamped_filename(tmp_path):
    service, _source, _backup_dir = make_backup_service(tmp_path)

    first = service.create_backup()
    second = service.create_backup()

    assert first != second


def test_list_backups_returns_newest_first(tmp_path):
    service, _source, _backup_dir = make_backup_service(tmp_path)
    service.create_backup()
    time.sleep(0.01)
    newest = service.create_backup()

    backups = service.list_backups()

    assert backups[0] == newest
    assert len(backups) == 2


def test_list_backups_ignores_files_that_are_not_backups(tmp_path):
    service, _source, backup_dir = make_backup_service(tmp_path)
    service.create_backup()
    (backup_dir / "random.txt").write_text("not a backup")

    backups = service.list_backups()

    assert len(backups) == 1
    assert all(file.name.startswith(BACKUP_FILENAME_PREFIX) for file in backups)


def test_rotation_keeps_only_the_newest_backups(tmp_path):
    service, _source, backup_dir = make_backup_service(tmp_path, keep=3)
    for _ in range(5):
        time.sleep(0.01)
        service.create_backup()

    remaining = sorted(backup_dir.iterdir())
    assert len(remaining) == 3
    assert service.list_backups() == remaining[::-1]


def test_rotation_never_grows_beyond_the_keep_limit(tmp_path):
    service, _source, _backup_dir = make_backup_service(tmp_path, keep=30)
    for _ in range(40):
        service.create_backup()

    assert len(service.list_backups()) == 30


def test_rotation_respects_a_small_keep_limit(tmp_path):
    service, _source, _backup_dir = make_backup_service(tmp_path, keep=1)
    service.create_backup()
    time.sleep(0.01)
    service.create_backup()

    backups = service.list_backups()
    assert len(backups) == 1


def test_keep_must_be_at_least_one(tmp_path):
    with pytest.raises(BackupError):
        BackupService(
            source_path=tmp_path / "db.sqlite",
            backup_dir=tmp_path / "backups",
            keep=0,
        )


def test_backup_on_startup_skips_when_there_is_no_database_file(tmp_path):
    service = BackupService(
        source_path=tmp_path / "missing.db",
        backup_dir=tmp_path / "backups",
        keep=3,
    )

    assert service.backup_on_startup() is None


def test_backup_on_startup_creates_a_backup_when_the_database_exists(tmp_path):
    service, _source, _backup_dir = make_backup_service(tmp_path)

    created = service.backup_on_startup()

    assert created is not None
    assert created.exists()


# ---------------------------------------------------------------------------
# SystemService — audit + shutdown wiring
# ---------------------------------------------------------------------------


def make_system(tmp_path, db, *, stopper=None, with_backups=True):
    source = tmp_path / "school_finance.db"
    source.write_bytes(b"sqlite-bytes")
    backup_dir = tmp_path / "backups"
    backups = (
        BackupService(source_path=source, backup_dir=backup_dir, keep=3)
        if with_backups
        else None
    )
    system = SystemService(db, audit=AuditService(db), backups=backups, stopper=stopper)
    return system


def test_backup_now_creates_a_backup_and_audits_it(tmp_path, db, session):
    system = make_system(tmp_path, db)

    created = system.backup_now(user=_user(session))

    assert created.exists()
    (entry,) = audit_actions(session, AuditActions.BACKUP_MANUAL)
    assert "backup" in entry.summary.lower()


def test_backup_now_without_a_backup_service_is_rejected_without_audit(tmp_path, db, session):
    system = make_system(tmp_path, db, with_backups=False)

    with pytest.raises(BackupError):
        system.backup_now(user=_user(session))

    assert audit_actions(session, AuditActions.BACKUP_MANUAL) == []


def test_backup_on_startup_audits_the_automatic_backup(tmp_path, db, session):
    system = make_system(tmp_path, db)

    created = system.backup_on_startup()

    assert created is not None
    (entry,) = audit_actions(session, AuditActions.BACKUP_AUTOMATIC)
    assert "startup" in entry.summary.lower()


def test_backup_on_startup_without_a_database_writes_no_audit_entry(tmp_path, db, session):
    source = tmp_path / "missing.db"
    backups = BackupService(source_path=source, backup_dir=tmp_path / "backups", keep=3)
    system = SystemService(db, audit=AuditService(db), backups=backups)

    assert system.backup_on_startup() is None
    assert audit_actions(session, AuditActions.BACKUP_AUTOMATIC) == []


def test_list_backups_describes_each_backup(tmp_path, db, session):
    system = make_system(tmp_path, db)
    system.backup_now(user=_user(session))

    backups = system.list_backups()

    assert len(backups) == 1
    info = backups[0]
    assert info.name.endswith(".db")
    assert info.size_bytes == len(b"sqlite-bytes")
    assert info.created_at is not None


def test_request_shutdown_audits_and_invokes_the_stopper(tmp_path, db, session):
    stopped = []
    system = make_system(tmp_path, db, stopper=lambda: stopped.append(True))

    system.request_shutdown(user=_user(session))

    assert stopped == [True]
    (entry,) = audit_actions(session, AuditActions.SHUTDOWN)
    assert "Head Teacher" in entry.summary


def test_request_shutdown_without_a_stopper_still_audits(tmp_path, db, session):
    system = make_system(tmp_path, db)

    system.request_shutdown(user=_user(session))

    assert len(audit_actions(session, AuditActions.SHUTDOWN)) == 1

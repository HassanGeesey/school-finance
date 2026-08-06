"""System service layer: backups and in-app shutdown.

Two concerns live here, both under the Admin's control:

**Backups** — the SQLite file is copied to a ``backups/`` folder automatically
on startup and on demand ("Backup now"), keeping the newest ~30 copies
(rotating: the oldest are removed). ``BackupService`` owns the file mechanics
(the single testing seam for rotation/ordering); ``SystemService`` wires it to
the audit log. Restore stays manual in v1 (copy a backup file back) per the spec.

**Shutdown** — an Admin can stop the running server from the UI. The request is
audited first (so the entry is durable before the process stops), then the
registered ``stopper`` callable is invoked. The default stopper asks the running
uvicorn server to stop gracefully; the packaged EXE (ticket 13) may inject its
own. Tests inject a recording stopper so they never stop the test runner.
"""

from __future__ import annotations

import os
import shutil
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import User

BACKUP_FILENAME_PREFIX = "school_finance"
BACKUP_FILENAME_SUFFIX = ".db"


class BackupError(Exception):
    """A backup could not be created or a backup service is not configured."""


def _backup_stamp() -> str:
    """UTC timestamp that sorts lexicographically and is unique per call."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


class BackupService:
    """File mechanics for the SQLite backups. No database dependency."""

    def __init__(self, *, source_path: Path, backup_dir: Path, keep: int = 30) -> None:
        if keep < 1:
            raise BackupError("At least one backup must be kept.")
        self._source_path = source_path
        self._backup_dir = backup_dir
        self._keep = keep

    def _files(self) -> list[Path]:
        """This service's backup files, oldest first (lexicographic by name)."""
        if not self._backup_dir.is_dir():
            return []
        return sorted(
            path
            for path in self._backup_dir.iterdir()
            if path.is_file()
            and path.name.startswith(BACKUP_FILENAME_PREFIX)
            and path.name.endswith(BACKUP_FILENAME_SUFFIX)
        )

    def create_backup(self) -> Path:
        """Copy the current database file into the backup folder, then rotate."""
        if not self._source_path.exists():
            raise BackupError(
                f"No database file at {self._source_path} to back up."
            )
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        dest = self._backup_dir / (
            f"{BACKUP_FILENAME_PREFIX}-{_backup_stamp()}{BACKUP_FILENAME_SUFFIX}"
        )
        shutil.copy2(self._source_path, dest)
        self.rotate()
        return dest

    def rotate(self) -> None:
        """Remove the oldest backups beyond the keep limit."""
        files = self._files()
        excess = len(files) - self._keep
        if excess > 0:
            for stale in files[:excess]:
                stale.unlink(missing_ok=True)

    def list_backups(self) -> list[Path]:
        """Backup files, newest first."""
        return list(reversed(self._files()))

    def backup_on_startup(self) -> Path | None:
        """Back up on startup. Returns ``None`` when there is no database file yet."""
        if not self._source_path.exists():
            return None
        return self.create_backup()


@dataclass(frozen=True)
class BackupInfo:
    """A backup file as shown on the settings page."""

    name: str
    path: Path
    size_bytes: int
    created_at: datetime


class SystemService:
    """Backup + shutdown business rules, each method one unit of work."""

    def __init__(
        self,
        db: Database,
        audit: AuditService | None = None,
        backups: BackupService | None = None,
        stopper: Callable[[], None] | None = None,
    ) -> None:
        self._db = db
        self._audit = audit
        self._backups = backups
        self._stopper = stopper

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    @property
    def backups_available(self) -> bool:
        return self._backups is not None

    # -- Backups -------------------------------------------------------------

    def backup_now(self, *, user: User | None) -> Path:
        """Create a backup on demand and record it in the audit log."""
        if self._backups is None:
            raise BackupError("Backups are not available for this instance.")
        path = self._backups.create_backup()
        self._log(
            user=user,
            action=AuditActions.BACKUP_MANUAL,
            summary=f"Manual backup created: {path.name}",
        )
        return path

    def backup_on_startup(self) -> Path | None:
        """Run the automatic startup backup (no-op when unavailable)."""
        if self._backups is None:
            return None
        path = self._backups.backup_on_startup()
        if path is not None:
            self._log(
                user=None,
                action=AuditActions.BACKUP_AUTOMATIC,
                summary=f"Automatic backup created on startup: {path.name}",
            )
        return path

    def list_backups(self) -> list[BackupInfo]:
        """The recent backups (newest first) for the settings page."""
        if self._backups is None:
            return []
        infos = []
        for path in self._backups.list_backups():
            stat = path.stat()
            infos.append(
                BackupInfo(
                    name=path.name,
                    path=path,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
        return infos

    # -- Shutdown ------------------------------------------------------------

    def request_shutdown(self, *, user: User | None) -> None:
        """Audit the shutdown request, then stop the server.

        The audit entry is committed before the stopper runs, so the record of
        who shut the app down is durable even though the process is about to end.
        """
        name = user.name if user is not None else "an operator"
        self._log(
            user=user,
            action=AuditActions.SHUTDOWN,
            summary=f"{name} shut down the app from the settings page",
        )
        if self._stopper is not None:
            self._stopper()


def _force_exit() -> None:
    """Last-resort exit: guarantee the process dies if graceful stop stalls."""
    time.sleep(5)
    os._exit(0)


def uvicorn_stop() -> None:
    """Gracefully stop the running uvicorn server.

    Uvicorn installs a SIGINT handler that sets ``should_exit``; raising SIGINT
    asks it to finish the current request and shut down. A daemon thread forces
    exit if the graceful stop ever stalls (e.g. a packaged, console-less EXE).
    Safe as a no-op when no server is listening.
    """
    delivered = False
    try:
        if os.name == "nt":
            os.kill(os.getpid(), signal.SIGINT)
            delivered = True
        else:
            signal.raise_signal(signal.SIGINT)
            delivered = True
    except (OSError, ValueError, TypeError):
        delivered = False
    if delivered:
        threading.Thread(target=_force_exit, name="shutdown-guard", daemon=True).start()

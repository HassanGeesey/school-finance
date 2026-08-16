"""Campus profile service layer: the acting Campus's identity and logos.

Each Campus owns its identity (multi-school ticket 07): the required campus
name plus optional contact details (address, phone, email, website) and the
uploaded logo's filename. ``ProfileService`` resolves the Campus it operates on
from the request scope — a Campus-bound role edits exactly its own Campus — or
from an explicit ``campus`` argument for non-request contexts (the setup
wizard, the demo seeder). Business rules live here; routes are thin adapters
(see ``app/profile/routes.py``).

**Logos** — the uploaded file is stored next to the app data (per
``docs/adr/0001-logo-in-data-dir.md``) as ``logo.<ext>``. ``LogoStorage`` owns
the file mechanics (the single testing seam for save/delete/media types);
``ProfileService`` wires it to the database and the audit log.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..audit.service import AuditActions, AuditService
from ..db import Database
from ..models import Campus, User
from ..tenants.scope import scope

# "Accept any image" per decision S-5, but only as a real image extension so the
# stored filename can never escape the data directory or mislead the browser.
ALLOWED_LOGO_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})

LOGO_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

# Magic bytes for the raster formats, so a file merely renamed to an image
# extension (e.g. a document saved as "logo.png") is refused. SVG is text, so
# the extension is its only guard — it never executes inside an ``<img>`` tag.
_RASTER_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}


class ProfileError(Exception):
    """Rejected input while editing the school profile."""


class LogoError(Exception):
    """A logo upload/removal could not be completed."""


class LogoStorage:
    """File mechanics for the uploaded logo. No database dependency."""

    def __init__(self, logo_dir: Path) -> None:
        self._logo_dir = logo_dir

    def save(self, data: bytes, *, source_name: str) -> str:
        """Persist the upload as ``logo.<ext>`` and return its filename.

        The extension is taken from an allowlist, so the filename is always a
        single safe name inside the logo directory. Raster files must also
        match their magic bytes so a mislabeled file is never stored.
        """
        extension = Path(source_name).suffix.lower()
        if extension not in ALLOWED_LOGO_EXTENSIONS:
            raise LogoError(
                "The logo must be an image (PNG, JPG, GIF, WEBP or SVG)."
            )
        self._verify_content(data, extension)
        self._logo_dir.mkdir(parents=True, exist_ok=True)
        filename = f"logo{extension}"
        (self._logo_dir / filename).write_bytes(data)
        return filename

    @staticmethod
    def _verify_content(data: bytes, extension: str) -> None:
        """Refuse files that are only renamed to a raster image extension."""
        magics = _RASTER_MAGIC.get(extension)
        if magics is None:
            return
        head = data[:16]
        if not any(head.startswith(magic) for magic in magics):
            raise LogoError(
                "The logo must be an image (PNG, JPG, GIF, WEBP or SVG)."
            )
        if extension == ".webp" and head[8:12] != b"WEBP":
            raise LogoError(
                "The logo must be an image (PNG, JPG, GIF, WEBP or SVG)."
            )

    def path(self, filename: str) -> Path:
        """The on-disk path for a stored logo filename."""
        return self._logo_dir / filename

    def remove(self, filename: str) -> None:
        """Delete a stored logo file if it exists."""
        self.path(filename).unlink(missing_ok=True)

    def media_type(self, filename: str) -> str:
        """The content type for serving a stored logo."""
        return LOGO_MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def logo_url_for(campus: Campus) -> str:
    """The serving URL for a Campus's logo, or ``""`` when none is set."""
    if not campus.logo_filename:
        return ""
    return f"/logos/{campus.logo_filename}"


class ProfileService:
    """Campus profile business rules. Each method is one unit of work.

    Every read/write resolves the target Campus from the request scope
    (Campus-bound roles edit their own Campus only) unless an explicit
    ``campus`` is passed. School-bound scopes (Superadmin/Owner) and unscoped
    calls have no Campus, so reads return ``None`` and writes raise.
    """

    def __init__(
        self,
        db: Database,
        audit: AuditService | None = None,
        logos: LogoStorage | None = None,
    ) -> None:
        self._db = db
        self._audit = audit
        self._logos = logos

    def _session(self) -> Session:
        return self._db.session()

    def _log(self, *, user: User | None, action: str, summary: str) -> None:
        if self._audit is not None:
            self._audit.log(user=user, action=action, summary=summary)

    def _campus_for(
        self, session: Session, *, campus: Campus | None = None
    ) -> Campus | None:
        """The Campus to operate on: the explicit one, else the scope's."""
        if campus is not None:
            return session.get(Campus, campus.id)
        sc = scope()
        if sc is None or sc.campus_id is None:
            return None
        return session.get(Campus, sc.campus_id)

    def get_profile(self, *, campus: Campus | None = None) -> Campus | None:
        """The acting scope's Campus identity, or ``None`` when it has none."""
        with self._session() as session:
            return self._campus_for(session, campus=campus)

    def update_profile(
        self,
        *,
        user: User | None,
        school_name: str,
        address: str = "",
        phone: str = "",
        email: str = "",
        website: str = "",
        campus: Campus | None = None,
    ) -> Campus:
        """Save the Campus's profile fields. The name can never be blank."""
        school_name = (school_name or "").strip()
        if not school_name:
            raise ProfileError("A school name is required.")

        with self._session() as session:
            campus = self._campus_for(session, campus=campus)
            if campus is None:
                raise ProfileError(
                    "No campus profile is available in this context."
                )
            changed: list[str] = []
            if (school_name or None) != campus.name:
                campus.name = school_name
                changed.append("school name")
            for label, new_value in (
                ("address", address.strip()),
                ("phone", phone.strip()),
                ("email", email.strip()),
                ("website", website.strip()),
            ):
                current = getattr(campus, label)
                if (new_value or None) != current:
                    setattr(campus, label, new_value or None)
                    changed.append(label)
            session.commit()
            session.refresh(campus)
            name = campus.name
        if not changed:
            return campus
        self._log(
            user=user,
            action=AuditActions.PROFILE_UPDATE,
            summary=f"School profile updated ({', '.join(sorted(set(changed)))}): {name}",
        )
        return campus

    def save_logo(
        self,
        *,
        user: User | None,
        data: bytes,
        source_name: str,
        campus: Campus | None = None,
    ) -> str:
        """Store a new logo file and record it, replacing the previous one."""
        if self._logos is None:
            raise LogoError("Logo storage is not available for this instance.")
        with self._session() as session:
            campus = self._campus_for(session, campus=campus)
            if campus is None:
                raise LogoError("No campus profile is available in this context.")
            old_filename = campus.logo_filename
            campus_id = campus.id
        filename = self._logos.save(data, source_name=source_name)
        with self._session() as session:
            target = session.get(Campus, campus_id)
            assert target is not None
            target.logo_filename = filename
            session.commit()
        if old_filename and old_filename != filename:
            self._logos.remove(old_filename)
        self._log(
            user=user,
            action=AuditActions.PROFILE_LOGO_UPLOAD,
            summary=f"Uploaded the school logo ({filename})",
        )
        return filename

    def remove_logo(self, *, user: User | None, campus: Campus | None = None) -> None:
        """Clear the logo: delete the file and forget its filename."""
        if self._logos is None:
            raise LogoError("Logo storage is not available for this instance.")
        with self._session() as session:
            campus = self._campus_for(session, campus=campus)
            if campus is None:
                raise LogoError("No campus profile is available in this context.")
            filename = campus.logo_filename
            campus.logo_filename = None
            session.commit()
        if filename:
            self._logos.remove(filename)
        self._log(
            user=user,
            action=AuditActions.PROFILE_LOGO_REMOVE,
            summary="Removed the school logo",
        )

    def logo_path(self, *, campus: Campus | None = None) -> Path | None:
        """The on-disk path of the scope's logo, or ``None`` when unset."""
        if self._logos is None:
            return None
        with self._session() as session:
            campus = self._campus_for(session, campus=campus)
            if campus is None or not campus.logo_filename:
                return None
            return self._logos.path(campus.logo_filename)

    def logo_media_type(self, *, campus: Campus | None = None) -> str:
        """The content type for serving the scope's logo."""
        if self._logos is None:
            return "application/octet-stream"
        with self._session() as session:
            campus = self._campus_for(session, campus=campus)
            if campus is None or not campus.logo_filename:
                return "application/octet-stream"
            return self._logos.media_type(campus.logo_filename)

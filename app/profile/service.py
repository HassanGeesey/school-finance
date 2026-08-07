"""School profile service layer: the school's identity, its editor, and logos.

The school's identity is a single-row ``school_profile`` record: the required
school name plus optional contact details (address, phone, email, website) and
the uploaded logo's filename. Business rules live here — routes are thin
adapters (see ``app/profile/routes.py``).

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
from ..models import SchoolProfile, User

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


def logo_url_for(profile: SchoolProfile) -> str:
    """The serving URL for a profile's logo, or ``""`` when none is set."""
    if not profile.logo_filename:
        return ""
    return f"/logos/{profile.logo_filename}"


class ProfileService:
    """School profile business rules. Each method is one unit of work."""

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

    def get_profile(self) -> SchoolProfile:
        """The single profile row, creating the empty record on first use.

        Older databases (set up before the profile existed) get a row here, so
        the settings page always has something to edit.
        """
        with self._session() as session:
            profile = self._get_or_create(session)
            session.commit()
            session.refresh(profile)
            return profile

    def update_profile(
        self,
        *,
        user: User | None,
        school_name: str,
        address: str = "",
        phone: str = "",
        email: str = "",
        website: str = "",
    ) -> SchoolProfile:
        """Save the profile fields. The school name can never be blank."""
        school_name = (school_name or "").strip()
        if not school_name:
            raise ProfileError("A school name is required.")

        with self._session() as session:
            profile = self._get_or_create(session)
            changed: list[str] = []
            if (school_name or None) != profile.school_name:
                profile.school_name = school_name
                changed.append("school name")
            for label, new_value in (
                ("address", address.strip()),
                ("phone", phone.strip()),
                ("email", email.strip()),
                ("website", website.strip()),
            ):
                current = getattr(profile, label)
                if (new_value or None) != current:
                    setattr(profile, label, new_value or None)
                    changed.append(label)
            session.commit()
            session.refresh(profile)
            name = profile.school_name
        if not changed:
            return profile
        self._log(
            user=user,
            action=AuditActions.PROFILE_UPDATE,
            summary=f"School profile updated ({', '.join(sorted(set(changed)))}): {name}",
        )
        return profile

    def save_logo(self, *, user: User | None, data: bytes, source_name: str) -> str:
        """Store a new logo file and record it, replacing the previous one."""
        if self._logos is None:
            raise LogoError("Logo storage is not available for this instance.")
        filename = self._logos.save(data, source_name=source_name)
        with self._session() as session:
            profile = self._get_or_create(session)
            old_filename = profile.logo_filename
            profile.logo_filename = filename
            session.commit()
        if old_filename and old_filename != filename:
            self._logos.remove(old_filename)
        self._log(
            user=user,
            action=AuditActions.PROFILE_LOGO_UPLOAD,
            summary=f"Uploaded the school logo ({filename})",
        )
        return filename

    def remove_logo(self, *, user: User | None) -> None:
        """Clear the logo: delete the file and forget its filename."""
        if self._logos is None:
            raise LogoError("Logo storage is not available for this instance.")
        with self._session() as session:
            profile = self._get_or_create(session)
            filename = profile.logo_filename
            profile.logo_filename = None
            session.commit()
        if filename:
            self._logos.remove(filename)
        self._log(
            user=user,
            action=AuditActions.PROFILE_LOGO_REMOVE,
            summary="Removed the school logo",
        )

    def logo_path(self) -> Path | None:
        """The on-disk path of the current logo, or ``None`` when unset."""
        filename = self.get_profile().logo_filename
        if self._logos is None or not filename:
            return None
        return self._logos.path(filename)

    def logo_media_type(self) -> str:
        """The content type for serving the current logo."""
        if self._logos is None:
            return "application/octet-stream"
        filename = self.get_profile().logo_filename
        if not filename:
            return "application/octet-stream"
        return self._logos.media_type(filename)

    @staticmethod
    def _get_or_create(session: Session) -> SchoolProfile:
        profile = session.get(SchoolProfile, 1)
        if profile is None:
            profile = SchoolProfile(id=1)
            session.add(profile)
        return profile

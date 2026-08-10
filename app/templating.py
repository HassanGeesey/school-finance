"""Shared template environment: the base layout's globals.

The app and the test mini-app (``tests/mini_app.py``) both build their
``Jinja2Templates`` through :func:`build_templates`, so the base layout always
gets the same globals no matter which factory created the app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from jinja2.runtime import Context

from .admin.service import USER_ROLE_LABELS
from .classes.service import CLASS_STATUS_LABELS
from .config import settings
from .models import User
from .money import format_cents, format_input_cents
from .profile.service import logo_url_for


def _register_template_globals(templates: Jinja2Templates) -> None:
    @pass_context
    def current_user(context: Context) -> User | None:
        request = context.get("request")
        if request is None:
            return None
        return getattr(request.state, "user", None)

    def role_label(role: str) -> str:
        return USER_ROLE_LABELS.get(role, role)

    def class_status_label(status: str) -> str:
        return CLASS_STATUS_LABELS.get(status, status)

    @pass_context
    def school_name(context: Context) -> str:
        """The school's name for the app shell, falling back to the product name.

        Setup and login override their title/brand explicitly with ``app_name``;
        everywhere else the school identity wins.
        """
        request = context.get("request")
        profile = getattr(request.state, "school_profile", None) if request is not None else None
        if profile is not None and profile.school_name:
            return profile.school_name
        return settings.APP_NAME

    @pass_context
    def logo_url(context: Context) -> str:
        """The serving URL for the current school logo, or "" when unset."""
        request = context.get("request")
        profile = getattr(request.state, "school_profile", None) if request is not None else None
        if profile is None:
            return ""
        return logo_url_for(profile)

    @pass_context
    def school_contact(context: Context) -> list[str]:
        """The profile's non-empty contact fields, in display order.

        Printed documents render only the fields that are actually set; blank
        contact fields never print (decision S-3/S-4).
        """
        request = context.get("request")
        profile = getattr(request.state, "school_profile", None) if request is not None else None
        if profile is None:
            return []
        return [
            value
            for value in (profile.address, profile.phone, profile.email, profile.website)
            if value
        ]

    templates.env.globals.update(
        app_name=settings.APP_NAME,
        app_version=settings.VERSION,
        year=datetime.now(timezone.utc).year,
        current_user=current_user,
        role_label=role_label,
        class_status_label=class_status_label,
        school_name=school_name,
        logo_url=logo_url,
        school_contact=school_contact,
        money=format_cents,
        money_input=format_input_cents,
    )


def build_templates(directory: Path) -> Jinja2Templates:
    """Create a template environment wired with the base layout's globals."""
    templates = Jinja2Templates(directory=str(directory))
    _register_template_globals(templates)
    return templates

"""Dependencies enforcing the session and role gates.

The session middleware resolves the token to a user on ``request.state.user``;
these dependencies read that state and either let the request through or stop it.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request

from ..models import User, UserRoles


def current_user(request: Request) -> User | None:
    """The logged-in user for this request, or None when logged out."""
    return getattr(request.state, "user", None)


def require_login(request: Request) -> User:
    """Gate: any page behind this dependency needs an active session."""
    user = current_user(request)
    if user is None:
        location = "/login?next=" + quote(request.url.path, safe="/")
        raise HTTPException(status_code=303, headers={"Location": location})
    return user


def require_admin(request: Request, user: User = Depends(require_login)) -> User:
    """Gate: configuration/admin pages need the Admin role."""
    if user.role != UserRoles.ADMIN:
        raise HTTPException(status_code=403, detail="This area requires the Admin role.")
    return user


def require_admin_or_superadmin(
    request: Request, user: User = Depends(require_login)
) -> User:
    """Gate: management/browse surfaces need the Admin or Superadmin role.

    The Campus Admin and the Superadmin both carry accountability over the
    audit trail (multi-school tickets 06): each browses the entries their scope
    allows. Finance Officers and Owners never reach these pages.
    """
    if user.role not in (UserRoles.ADMIN, UserRoles.SUPERADMIN):
        raise HTTPException(
            status_code=403,
            detail="This area requires the Admin or Superadmin role.",
        )
    return user

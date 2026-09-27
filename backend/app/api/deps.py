from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthService, SessionContext

DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return None


def get_session_context(request: Request, db: DbSession) -> SessionContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return AuthService(db).resolve_session(token)


def require_session(
    request: Request, db: DbSession
) -> SessionContext:
    context = get_session_context(request, db)
    if context is None:
        raise errors.unauthorized()
    return context


def get_current_user(
    context: Annotated[SessionContext, Depends(require_session)]
) -> User:
    """The only source of the acting user id: the server side session."""
    return context.user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSession = Annotated[SessionContext, Depends(require_session)]


def require_owner(user: CurrentUser) -> User:
    if user.role != UserRole.OWNER.value:
        raise errors.forbidden("Bu işlem yalnızca owner kullanıcı içindir.")
    return user


OwnerUser = Annotated[User, Depends(require_owner)]


def verify_csrf(request: Request, db: DbSession) -> None:
    """Double submit CSRF check.

    Only enforced when a session cookie is present: unauthenticated endpoints
    (login, invitation acceptance) carry no ambient authority, so there is
    nothing to forge.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return
    session = AuthService(db).sessions.get_active_by_token(token)
    if session is None:
        # Expired / revoked cookie: let the endpoint answer 401.
        return
    provided = request.headers.get(settings.csrf_header_name)
    AuthService(db).verify_csrf(session, provided)


# --- cookie helpers ----------------------------------------------------
def set_session_cookies(response: Response, context: SessionContext) -> None:
    max_age = settings.session_ttl_days * 24 * 3600
    response.set_cookie(
        key=settings.session_cookie_name,
        value=context.session_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=context.csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            key=name, path="/", domain=settings.cookie_domain, samesite="lax"
        )


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        domain=settings.cookie_domain,
        path="/",
    )

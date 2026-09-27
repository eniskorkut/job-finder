from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    CurrentUser,
    DbSession,
    OwnerUser,
    clear_session_cookies,
    client_ip,
    set_csrf_cookie,
    set_session_cookies,
)
from app.core import errors
from app.core.config import settings
from app.core.security import generate_token
from app.models.enums import UserRole
from app.schemas.auth import (
    ChangePasswordRequest,
    CsrfResponse,
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationPublic,
    InvitationRead,
    LoginRequest,
    SessionResponse,
    SessionUserRead,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService
from app.services.invitation_service import InvitationService
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfResponse)
def issue_csrf_token(request: Request, response: Response) -> CsrfResponse:
    """Ensure a CSRF cookie exists so the SPA can send the header."""
    existing = request.cookies.get(settings.csrf_cookie_name)
    token = existing or generate_token()
    if not existing:
        set_csrf_cookie(response, token)
    return CsrfResponse(csrf_token=token)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> SessionResponse:
    auth = AuthService(db)
    auth.enforce_login_rate_limit(payload.identifier, client_ip(request))
    try:
        user = auth.authenticate(payload.identifier, payload.password)
    except errors.AppError as exc:
        if exc.status_code in {401, 403}:
            auth.register_failed_login(payload.identifier, client_ip(request))
        raise

    context = auth.create_session(
        user, user_agent=request.headers.get("user-agent"), ip_address=client_ip(request)
    )
    auth.reset_login_rate_limit(payload.identifier, client_ip(request))
    db.commit()
    set_session_cookies(response, context)
    return SessionResponse(
        user=SessionUserRead.model_validate(user), csrf_token=context.csrf_token
    )


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: DbSession) -> MessageResponse:
    token = request.cookies.get(settings.session_cookie_name)
    auth = AuthService(db)
    if token:
        auth.revoke_session(token)
        db.commit()
    clear_session_cookies(response)
    return MessageResponse(message="Çıkış yapıldı.", code="logged_out")


@router.get("/session", response_model=SessionResponse)
def read_session(request: Request, db: DbSession) -> SessionResponse:
    token = request.cookies.get(settings.session_cookie_name)
    context = AuthService(db).resolve_session(token) if token else None
    if context is None:
        raise errors.unauthorized()
    db.commit()
    return SessionResponse(
        user=SessionUserRead.model_validate(context.user), csrf_token=""
    )


@router.post("/password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    auth = AuthService(db)
    auth.change_password(session_user, payload.current_password, payload.new_password)
    # Password change invalidates every existing session, then hands the
    # current browser a brand new one.
    auth.revoke_all_sessions(session_user.id)
    context = auth.create_session(
        session_user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    db.commit()
    set_session_cookies(response, context)
    return MessageResponse(message="Parola güncellendi.", code="password_changed")


# --- invitations -------------------------------------------------------
@router.get("/invitations", response_model=list[InvitationRead])
def list_invitations(owner: OwnerUser, db: DbSession) -> list[InvitationRead]:
    service = InvitationService(db)
    now = datetime.now(timezone.utc)
    items: list[InvitationRead] = []
    for invitation in service.list_invitations():
        item = InvitationRead.model_validate(invitation)
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if invitation.used_at is not None:
            item.status = "used"
        elif expires_at <= now:
            item.status = "expired"
        else:
            item.status = "pending"
        items.append(item)
    return items


@router.post(
    "/invitations", response_model=InvitationRead, status_code=status.HTTP_201_CREATED
)
def create_invitation(
    payload: InvitationCreateRequest, owner: OwnerUser, db: DbSession
) -> InvitationRead:
    service = InvitationService(db)
    invitation, token = service.create_invitation(
        owner,
        email=str(payload.email),
        note=payload.note,
        expires_in_hours=payload.expires_in_hours,
    )
    db.commit()
    item = InvitationRead.model_validate(invitation)
    item.status = "pending"
    item.invite_url = (
        f"{settings.frontend_url.rstrip('/')}/invite/{token}"
    )
    return item


@router.delete("/invitations/{invitation_id}", response_model=MessageResponse)
def revoke_invitation(
    invitation_id: uuid.UUID, owner: OwnerUser, db: DbSession
) -> MessageResponse:
    InvitationService(db).revoke_invitation(owner, invitation_id)
    db.commit()
    return MessageResponse(message="Davet iptal edildi.", code="invitation_revoked")


@router.get("/invitations/{token}/inspect", response_model=InvitationPublic)
def inspect_invitation(token: str, db: DbSession) -> InvitationPublic:
    invitation, problem = InvitationService(db).inspect(token)
    if invitation is None:
        return InvitationPublic(
            email="invalid@example.com",
            expires_at=datetime.now(timezone.utc),
            is_valid=False,
            message=problem,
        )
    return InvitationPublic(
        email=invitation.email,
        expires_at=invitation.expires_at,
        is_valid=problem is None,
        invited_by=invitation.invited_by.full_name or invitation.invited_by.username,
        message=problem,
    )


@router.post(
    "/invitations/accept",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_invitation(
    payload: InvitationAcceptRequest, request: Request, response: Response, db: DbSession
) -> SessionResponse:
    service = InvitationService(db)
    user = service.accept(
        token=payload.token,
        username=str(payload.username),
        password=payload.password,
        email=str(payload.email) if payload.email else None,
        full_name=payload.full_name,
    )
    auth = AuthService(db)
    context = auth.create_session(
        user, user_agent=request.headers.get("user-agent"), ip_address=client_ip(request)
    )
    db.commit()
    set_session_cookies(response, context)
    return SessionResponse(
        user=SessionUserRead.model_validate(user), csrf_token=context.csrf_token
    )


@router.get("/users", response_model=list[SessionUserRead])
def list_users(owner: OwnerUser, db: DbSession) -> list[SessionUserRead]:
    """Small helper for the two-user deployment (owner only)."""
    users = UserService(db).users.list_all()
    for user in users:
        if user.role not in {UserRole.OWNER.value, UserRole.MEMBER.value}:
            user.role = UserRole.MEMBER.value
    return [SessionUserRead.model_validate(user) for user in users]

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.core.security import (
    INVITATION_TOKEN_BYTES,
    generate_token,
    hash_password,
    hash_token,
)
from app.models.enums import UserRole
from app.models.user import User, UserInvitation
from app.repositories.invitations import InvitationRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.users import UserRepository
from app.services.auth_service import AuthService


class InvitationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.invitations = InvitationRepository(db)
        self.users = UserRepository(db)
        self.preferences = PreferenceRepository(db)
        self.auth = AuthService(db)

    # --- creation / listing -------------------------------------------
    def create_invitation(
        self,
        inviter: User,
        *,
        email: str,
        note: str | None = None,
        expires_in_hours: int | None = None,
    ) -> tuple[UserInvitation, str]:
        if inviter.role != UserRole.OWNER.value:
            raise errors.forbidden("Yalnızca ilk kullanıcı (owner) davet gönderebilir.")
        if self.users.email_exists(email):
            raise errors.conflict("Bu e-posta ile kayıtlı bir kullanıcı zaten var.")

        token = generate_token(INVITATION_TOKEN_BYTES)
        ttl_hours = expires_in_hours or settings.invitation_ttl_hours
        invitation = UserInvitation(
            email=email.strip().lower(),
            token_hash=hash_token(token),
            invited_by_user_id=inviter.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            note=note,
        )
        self.db.add(invitation)
        self.db.flush()
        return invitation, token

    def list_invitations(self) -> list[UserInvitation]:
        return self.invitations.list_all()

    def revoke_invitation(self, inviter: User, invitation_id: uuid.UUID) -> None:
        if inviter.role != UserRole.OWNER.value:
            raise errors.forbidden("Yalnızca ilk kullanıcı (owner) davetleri yönetebilir.")
        invitation = self.invitations.get_for_user(invitation_id)
        if invitation is None:
            raise errors.not_found("Davet bulunamadı.")
        if invitation.used_at is not None:
            raise errors.conflict("Kullanılmış davet iptal edilemez.")
        self.db.delete(invitation)
        self.db.flush()

    # --- inspection / acceptance --------------------------------------
    def inspect(self, token: str) -> tuple[UserInvitation | None, str | None]:
        invitation = self.invitations.get_by_token(token)
        if invitation is None:
            return None, "Davet bağlantısı geçersiz."
        if invitation.used_at is not None:
            return invitation, "Bu davet bağlantısı daha önce kullanılmış."
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return invitation, "Davet bağlantısının süresi dolmuş."
        return invitation, None

    def accept(
        self,
        *,
        token: str,
        username: str,
        password: str,
        email: str | None = None,
        full_name: str | None = None,
    ) -> User:
        invitation, problem = self.inspect(token)
        if invitation is None or problem is not None:
            raise errors.validation_error(problem or "Davet bağlantısı geçersiz.")

        final_email = (email or invitation.email).strip().lower()
        if final_email != invitation.email:
            raise errors.validation_error(
                "Davet yalnızca davet edilen e-posta adresi ile kabul edilebilir."
            )
        if self.users.username_exists(username):
            raise errors.conflict("Bu kullanıcı adı zaten alınmış.")
        if self.users.email_exists(final_email):
            raise errors.conflict("Bu e-posta ile kayıtlı bir kullanıcı zaten var.")

        user = User(
            username=username.strip(),
            email=final_email,
            password_hash=hash_password(password),
            full_name=(full_name or "").strip() or None,
            role=UserRole.MEMBER.value,
        )
        self.db.add(user)
        self.db.flush()
        self.preferences.get_or_create(user)

        # Single use: mark consumed before the caller commits.
        invitation.used_at = datetime.now(timezone.utc)
        invitation.used_by_user_id = user.id
        self.db.flush()
        return user

    def purge_expired(self) -> int:
        return self.invitations.delete_expired()

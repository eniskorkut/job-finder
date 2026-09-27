from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter
from app.core.security import (
    CSRF_TOKEN_BYTES,
    SESSION_TOKEN_BYTES,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User, UserSession
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository

login_limiter = SlidingWindowRateLimiter(
    max_attempts=settings.login_rate_limit_attempts,
    window_seconds=settings.login_rate_limit_window_seconds,
)


@dataclass(slots=True)
class SessionContext:
    user: User
    session: UserSession
    session_token: str
    csrf_token: str


class AuthService:
    """Session/password logic. Ownership is always derived from the session."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    # --- login ---------------------------------------------------------
    def rate_limit_key(self, identifier: str, client_ip: str | None) -> str:
        return f"{client_ip or 'unknown'}:{identifier.strip().lower()}"

    def enforce_login_rate_limit(self, identifier: str, client_ip: str | None) -> None:
        allowed, retry_after = login_limiter.check(
            self.rate_limit_key(identifier, client_ip)
        )
        if not allowed:
            raise errors.rate_limited(
                f"Çok fazla başarısız giriş denemesi. {retry_after} saniye sonra tekrar deneyin.",
                retry_after=retry_after,
            )

    def register_failed_login(self, identifier: str, client_ip: str | None) -> None:
        login_limiter.hit(self.rate_limit_key(identifier, client_ip))

    def reset_login_rate_limit(self, identifier: str, client_ip: str | None) -> None:
        login_limiter.reset(self.rate_limit_key(identifier, client_ip))

    def authenticate(self, identifier: str, password: str) -> User:
        user = self.users.get_by_identifier(identifier)
        if user is None:
            # Constant-ish work factor: still hash to avoid trivial user probing.
            hash_password(password)
            raise errors.unauthorized("Kullanıcı adı/e-posta veya parola hatalı.")
        if not user.is_active:
            raise errors.forbidden("Hesap devre dışı bırakılmış.")
        if not verify_password(password, user.password_hash):
            raise errors.unauthorized("Kullanıcı adı/e-posta veya parola hatalı.")
        self.users.touch_last_login(user)
        return user

    def create_session(
        self,
        user: User,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionContext:
        token = generate_token(SESSION_TOKEN_BYTES)
        csrf_token = generate_token(CSRF_TOKEN_BYTES)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)

        session = UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_hash=hash_token(csrf_token),
            user_agent=(user_agent or "")[:255] or None,
            ip_address=(ip_address or "")[:64] or None,
            expires_at=expires_at,
        )
        self.db.add(session)
        self.db.flush()
        return SessionContext(
            user=user, session=session, session_token=token, csrf_token=csrf_token
        )

    # --- session resolution -------------------------------------------
    def resolve_session(self, token: str | None) -> SessionContext | None:
        if not token:
            return None
        session = self.sessions.get_active_by_token(token)
        if session is None:
            return None
        user = self.users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            return None
        self.sessions.touch(session)
        return SessionContext(
            user=user, session=session, session_token=token, csrf_token=""
        )

    def verify_csrf(self, session: UserSession, provided: str | None) -> None:
        if not provided:
            raise errors.forbidden("CSRF doğrulaması başarısız: token eksik.")
        if hash_token(provided) != session.csrf_hash:
            raise errors.forbidden("CSRF doğrulaması başarısız.")

    def revoke_session(self, token: str) -> None:
        session = self.sessions.get_by_token(token)
        if session is not None and session.revoked_at is None:
            self.sessions.revoke(session)

    def revoke_all_sessions(self, user_id: uuid.UUID, *, keep: uuid.UUID | None = None) -> None:
        if keep is None:
            self.sessions.revoke_all_for_user(user_id)
            return
        for session in self.sessions.list_for_user(user_id):
            if session.id != keep and session.revoked_at is None:
                self.sessions.revoke(session)

    # --- password ------------------------------------------------------
    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise errors.validation_error("Mevcut parola hatalı.")
        if verify_password(new_password, user.password_hash):
            raise errors.validation_error("Yeni parola mevcut parolayla aynı olamaz.")
        user.password_hash = hash_password(new_password)
        self.db.flush()

    def set_password(self, user: User, new_password: str) -> None:
        user.password_hash = hash_password(new_password)
        self.db.flush()

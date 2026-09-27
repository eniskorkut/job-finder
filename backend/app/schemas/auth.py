from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,50}$"


def _validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Parola en az {PASSWORD_MIN_LENGTH} karakter olmalı.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Parola en fazla {PASSWORD_MAX_LENGTH} karakter olabilir.")
    if value.lower() in {"password12", "1234567890", "parola1234"}:
        raise ValueError("Bu parola çok yaygın, farklı bir parola seçin.")
    return value


class LoginRequest(BaseModel):
    identifier: str = Field(
        min_length=3, max_length=320, description="Kullanıcı adı veya e-posta"
    )

    @field_validator("identifier")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class SessionUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class SessionResponse(BaseModel):
    user: SessionUserRead
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    _check_password = field_validator("new_password")(_validate_password)


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    note: str | None = Field(default=None, max_length=300)
    expires_in_hours: int | None = Field(default=None, ge=1, le=720)


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    status: str = "pending"
    invite_url: str | None = None


class InvitationPublic(BaseModel):
    email: EmailStr
    expires_at: datetime
    is_valid: bool
    invited_by: str | None = None
    message: str | None = None


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    username: str = Field(pattern=USERNAME_PATTERN)
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    _check_password = field_validator("password")(_validate_password)

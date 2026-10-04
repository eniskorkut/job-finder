from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    """HTTP error carrying a machine readable ``code`` and a human message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        detail: dict[str, Any] = {"code": code, "message": message}
        if extra:
            detail.update(extra)
        super().__init__(status_code=status_code, detail=detail)


def unauthorized(message: str = "Oturum bulunamadı. Lütfen giriş yapın.") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, "unauthorized", message)


def forbidden(message: str = "Bu işlem için yetkiniz yok.") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, "forbidden", message)


def not_found(message: str = "Kayıt bulunamadı.") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, "not_found", message)


def conflict(message: str) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, "conflict", message)


def validation_error(
    message: str,
    code: str = "validation_error",
    *,
    extra: dict[str, Any] | None = None,
) -> AppError:
    return AppError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, code, message, extra=extra
    )


def rate_limited(message: str, retry_after: int | None = None) -> AppError:
    extra = {"retry_after": retry_after} if retry_after is not None else None
    return AppError(
        status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", message, extra=extra
    )


def not_implemented(phase: str, message: str) -> AppError:
    return AppError(
        status.HTTP_501_NOT_IMPLEMENTED,
        "not_implemented",
        message,
        extra={"phase": phase},
    )


def service_unavailable(
    message: str = "Servis şu anda kullanılamıyor.",
    code: str = "service_unavailable",
    *,
    extra: dict[str, Any] | None = None,
) -> AppError:
    return AppError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        code,
        message,
        extra=extra,
    )


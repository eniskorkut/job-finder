from __future__ import annotations

from app.models.enums import ErrorClass


class ProviderError(RuntimeError):
    """A provider call failed. ``error_class`` drives the retry/idempotency logic."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        error_class: ErrorClass = ErrorClass.TRANSIENT,
        status_code: int | None = None,
        retry_after: float | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.error_class = error_class
        self.status_code = status_code
        self.retry_after = retry_after
        self.retryable = (
            retryable
            if retryable is not None
            else error_class in {ErrorClass.TRANSIENT, ErrorClass.RATE_LIMIT}
        )


class CursorExpiredError(ProviderError):
    """The stored incremental cursor is no longer accepted by the provider."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(
            message,
            provider=provider,
            error_class=ErrorClass.CURSOR_EXPIRED,
            retryable=False,
        )


class ProviderAuthError(ProviderError):
    def __init__(self, message: str, *, provider: str, status_code: int = 401) -> None:
        super().__init__(
            message,
            provider=provider,
            error_class=ErrorClass.AUTH,
            status_code=status_code,
            retryable=False,
        )


class DisallowedHostError(ProviderError):
    """A continuation link pointed somewhere we refuse to send a token to."""

    def __init__(self, url: str, *, provider: str) -> None:
        from urllib.parse import urlsplit

        host = urlsplit(url).netloc
        super().__init__(
            f"İzin verilmeyen adres reddedildi: {host or 'geçersiz adres'}",
            provider=provider,
            error_class=ErrorClass.PERMANENT,
            retryable=False,
        )

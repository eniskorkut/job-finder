"""Log hygiene: provider tokens must never reach a log line.

``httpx`` logs full request URLs at INFO level, and Telegram keeps its bot
token in the URL path. This filter rewrites the message before it is emitted,
so no code path can leak the token by accident.
"""

from __future__ import annotations

import logging
import re

# Telegram tokens appear both inside URLs (``/bot<id>:<secret>/method``) and as
# bare values in log arguments, so both shapes are redacted.
_BOT_URL_TOKEN_RE = re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{10,}")
_BARE_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{10,}\b")
_SAFE_URL = "bot<redacted>"
_SAFE_BARE = "<redacted-token>"


def redact(value: str) -> str:
    return _BARE_TOKEN_RE.sub(_SAFE_BARE, _BOT_URL_TOKEN_RE.sub(_SAFE_URL, value))


class SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redact(arg) if isinstance(arg, str) else arg for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    key: redact(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
        except Exception:  # pragma: no cover - logging must never raise
            return True
        return True


_installed = False


def install_secret_filter(logger_names: tuple[str, ...] = ("httpx", "httpcore", "jobhunter")) -> None:
    """Attach the filter once per process (API and worker both call it)."""
    global _installed
    if _installed:
        return
    secret_filter = SecretRedactingFilter()
    for name in logger_names:
        logging.getLogger(name).addFilter(secret_filter)
    logging.getLogger().addFilter(secret_filter)
    _installed = True

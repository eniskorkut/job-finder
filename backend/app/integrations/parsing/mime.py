"""MIME decoding shared by every provider.

Providers hand us bytes (Gmail ``format=raw``, Graph ``$value``) or JSON with a
body; both are normalised to :class:`~app.integrations.base.RawMessage` here so
parsers never deal with provider specifics.
"""

from __future__ import annotations

import email
import email.policy
import re
from datetime import datetime, timezone
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup

from app.integrations.base import RawMessage

WHITESPACE_RE = re.compile(r"[ \t\u00a0\u200b]+")


def html_to_text(html: str) -> str:
    """HTML -> readable text: unescape entities, keep block boundaries."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for br in soup.find_all(["br", "p", "div", "li", "tr", "table", "h1", "h2", "h3"]):
        br.insert_after("\n")
    text = soup.get_text("\n")
    return collapse_whitespace(text)


def collapse_whitespace(text: str) -> str:
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _decode_part(part: Message) -> str | None:
    try:
        payload = part.get_payload(decode=True)
    except Exception:  # pragma: no cover - malformed headers
        return None
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else None

    charset = part.get_content_charset() or "utf-8"
    for candidate in (charset, "utf-8", "cp1254", "latin-1"):
        try:
            return payload.decode(candidate, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def _iter_parts(message: Message):
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment":
                continue
            yield part
    else:
        yield message


def parse_message_bytes(raw: bytes, *, external_id: str) -> RawMessage:
    """Decode a full RFC 822 message (any charset / transfer encoding)."""
    message = email.message_from_bytes(raw, policy=email.policy.default)

    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in _iter_parts(message):
        content_type = (part.get_content_type() or "").lower()
        if content_type == "text/plain":
            decoded = _decode_part(part)
            if decoded:
                plain_parts.append(decoded)
        elif content_type == "text/html":
            decoded = _decode_part(part)
            if decoded:
                html_parts.append(decoded)

    body_text = collapse_whitespace("\n".join(plain_parts)).strip()
    body_html = "\n".join(html_parts).strip() or None

    if not body_text and body_html:
        body_text = html_to_text(body_html)
    if not body_text and not body_html:
        fallback = _decode_part(message)
        body_text = collapse_whitespace(fallback or "").strip()

    subject = str(message.get("subject") or "").strip()
    sender_raw = str(message.get("from") or "").strip()
    sender = parseaddr(sender_raw)[1] or sender_raw

    received_at = _parse_date(str(message.get("date") or ""))

    headers = {
        key.lower(): str(value)
        for key, value in message.items()
        if key.lower() in {"from", "to", "subject", "date", "message-id", "list-unsubscribe"}
    }

    return RawMessage(
        external_id=external_id,
        subject=subject,
        sender=sender,
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
        headers=headers,
    )


def _parse_date(value: str) -> datetime:
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed is not None:
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            pass
    return datetime.now(timezone.utc)


def build_raw_message(
    *,
    external_id: str,
    subject: str,
    sender: str,
    received_at: datetime,
    text: str | None = None,
    html: str | None = None,
) -> RawMessage:
    """Fallback path for providers that return pre-parsed JSON bodies."""
    body_text = collapse_whitespace(text or "").strip()
    body_html = html.strip() if html else None
    if not body_text and body_html:
        body_text = html_to_text(body_html)
    return RawMessage(
        external_id=external_id,
        subject=subject.strip(),
        sender=sender.strip(),
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
    )

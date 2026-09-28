"""Personal data minimisation before any LLM call.

Matching only needs skills and experience, so contact details and government
identifiers are stripped from the CV text before it leaves the server (and
before it is cached in a profile).
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\s?90[\s.-]?)?(?:\(?0?[2-5]\d{2}\)?[\s.-]?)\d{3}[\s.-]?\d{2}[\s.-]?\d{2}"
)
TCKN_RE = re.compile(r"\b[1-9]\d{10}\b")
IBAN_RE = re.compile(r"\bTR\d{2}\s?(?:\d{4}\s?){5}\d{2}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
ADDRESS_HINT_RE = re.compile(
    r"(?im)^\s*(adres|address|ikametgah)\s*[:\-].*$",
)

PLACEHOLDERS = {
    "email": "[e-posta gizlendi]",
    "phone": "[telefon gizlendi]",
    "tckn": "[kimlik no gizlendi]",
    "iban": "[iban gizlendi]",
    "address": "[adres gizlendi]",
}


def redact_pii(text: str | None) -> str:
    """Remove contact and identity data; keep the professional content."""
    if not text:
        return ""
    value = EMAIL_RE.sub(PLACEHOLDERS["email"], text)
    value = PHONE_RE.sub(PLACEHOLDERS["phone"], value)
    value = IBAN_RE.sub(PLACEHOLDERS["iban"], value)
    value = TCKN_RE.sub(PLACEHOLDERS["tckn"], value)
    value = ADDRESS_HINT_RE.sub(PLACEHOLDERS["address"], value)
    # URLs rarely matter for matching and can carry tracking identifiers.
    value = URL_RE.sub("[bağlantı gizlendi]", value)
    return value


def redact_job_text(text: str | None) -> str:
    """Job postings are public, but never let tracking URLs reach the model."""
    if not text:
        return ""
    return URL_RE.sub("[bağlantı gizlendi]", text)

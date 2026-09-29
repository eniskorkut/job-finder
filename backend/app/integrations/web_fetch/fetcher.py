"""Web fetch integration with strict SSRF protection and LinkedIn fetch guard."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings
from app.services.job_enrichment.url_utils import is_linkedin_url

logger = logging.getLogger("jobhunter.web_fetch")

CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/ld+json",
    "text/plain",
    "text/xml",
    "application/xml",
    "application/json",
)


class WebFetchError(Exception):
    """Base exception for web fetch errors."""


class SSRFProtectionError(WebFetchError):
    """Raised when a URL attempts to target a private, loopback, or metadata address."""


class LinkedInFetchForbiddenError(WebFetchError):
    """Raised when attempting to fetch LinkedIn (scraping LinkedIn is strictly prohibited)."""


class ResponseTooLargeError(WebFetchError):
    """Raised when a response exceeds the maximum allowed payload size."""


class InvalidContentTypeError(WebFetchError):
    """Raised when the fetched content is not an accepted text or document format."""


class TooManyRedirectsError(WebFetchError):
    """Raised when the redirect hop limit is exceeded."""


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content: str
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = ""


def is_ip_prohibited(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, multicast, or metadata."""
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.version == 4 and ip in CARRIER_GRADE_NAT:
        return True
    # Explicit cloud metadata check (169.254.169.254)
    if str(ip) == "169.254.169.254":
        return True
    return False


async def validate_url_for_ssrf(url: str) -> None:
    """Strictly validate URL structure, scheme, hostname, and resolved IP against SSRF."""
    if not url or not isinstance(url, str):
        raise SSRFProtectionError("Boş veya geçersiz URL.")

    try:
        parts = urlsplit(url.strip())
    except Exception as exc:
        raise SSRFProtectionError(f"URL ayrıştırılamadı: {exc}") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFProtectionError(f"Desteklenmeyen URL şeması: {parts.scheme}. Sadece http/https izinlidir.")

    # Disallow userinfo (http://user:pass@host)
    if parts.username or parts.password or ("@" in (parts.netloc.split(":")[0])):
        raise SSRFProtectionError("URL içerisinde kimlik bilgisi (userinfo) bulunamaz.")

    host = parts.hostname
    if not host:
        raise SSRFProtectionError("URL geçerli bir sunucu adı (host) içermelidir.")

    host_lower = host.lower()

    # Reject local/internal hosts
    if host_lower in {"localhost", "0.0.0.0", "127.0.0.1", "::1"} or (
        host_lower.endswith(".local") or host_lower.endswith(".internal") or host_lower.endswith(".localhost")
    ):
        raise SSRFProtectionError(f"Erişime kapalı yerel adres: {host}")

    # Reject cloud metadata hostnames
    if "metadata.google.internal" in host_lower or "169.254.169.254" in host_lower:
        raise SSRFProtectionError(f"Bulut metadata servisi erişimi engellendi: {host}")

    # NEVER SCRAPE LINKEDIN!
    if is_linkedin_url(url):
        raise LinkedInFetchForbiddenError(
            f"LinkedIn sayfalarını çekmek kesinlikle yasaktır ({url}). "
            "LinkedIn bağlantıları yalnızca gezinme bağlantısı olarak kullanıcıya sunulur."
        )

    # Resolve hostname via DNS and check all resolved IPs
    loop = asyncio.get_running_loop()
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        addr_info = await loop.getaddrinfo(
            host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SSRFProtectionError(f"DNS çözümleme başarısız ({host}): {exc}") from exc

    if not addr_info:
        raise SSRFProtectionError(f"Sunucu için IP adresi bulunamadı ({host}).")

    for entry in addr_info:
        ip_str = entry[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFProtectionError(f"Geçersiz IP adresi ({ip_str}): {exc}") from exc

        if is_ip_prohibited(ip_obj):
            raise SSRFProtectionError(
                f"Sunucu '{host}' erişimi engellenen özel/dahili IP adresine çözümlendi: {ip_str}"
            )


class SafeWebFetcher:
    """Safe, bounded web fetcher with SSRF guards, manual redirect validation,
    size limits, and strict LinkedIn fetch prohibition.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        max_concurrency: int | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds or settings.web_fetch_timeout_seconds
        self.max_bytes = max_bytes or settings.web_fetch_max_bytes
        self.max_redirects = max_redirects or settings.web_fetch_max_redirects
        self.semaphore = asyncio.Semaphore(
            max(1, max_concurrency or settings.web_fetch_max_concurrency)
        )
        self.user_agent = user_agent or settings.web_fetch_user_agent

    async def fetch(self, url: str) -> FetchResult:
        """Fetch URL content with strict SSRF validation on every redirect hop."""
        async with self.semaphore:
            current_url = url
            hop = 0

            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/ld+json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
            }

            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(self.timeout_seconds),
                verify=True,
            ) as client:
                while True:
                    await validate_url_for_ssrf(current_url)

                    try:
                        async with client.stream("GET", current_url, headers=headers) as response:
                            # Handle redirects manually to validate each target hop
                            if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                                hop += 1
                                if hop > self.max_redirects:
                                    raise TooManyRedirectsError(
                                        f"Yönlendirme sınırı ({self.max_redirects}) aşıldı."
                                    )
                                location = response.headers.get("location")
                                if not location:
                                    raise WebFetchError("Yönlendirme yanıtında Location başlığı eksik.")
                                current_url = urljoin(current_url, location)
                                logger.debug("Yönlendirme izleniyor (hop=%d): %s", hop, current_url)
                                continue

                            # Validate Content-Type
                            raw_content_type = response.headers.get("content-type", "").lower()
                            base_content_type = raw_content_type.split(";")[0].strip()
                            if base_content_type and not any(
                                base_content_type.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES
                            ):
                                raise InvalidContentTypeError(
                                    f"Desteklenmeyen içerik türü: {raw_content_type}"
                                )

                            # Validate Content-Length if present
                            content_length_hdr = response.headers.get("content-length")
                            if content_length_hdr and content_length_hdr.isdigit():
                                if int(content_length_hdr) > self.max_bytes:
                                    raise ResponseTooLargeError(
                                        f"İçerik boyutu ({content_length_hdr} byte) {self.max_bytes} byte sınırını aşıyor."
                                    )

                            # Stream and enforce maximum byte limit
                            body_chunks = []
                            total_bytes = 0
                            async for chunk in response.aiter_bytes():
                                total_bytes += len(chunk)
                                if total_bytes > self.max_bytes:
                                    raise ResponseTooLargeError(
                                        f"İçerik akışı azami sınırı ({self.max_bytes} byte) aştı."
                                    )
                                body_chunks.append(chunk)

                            raw_body = b"".join(body_chunks)
                            # Decode text
                            encoding = response.encoding or "utf-8"
                            try:
                                text_content = raw_body.decode(encoding, errors="replace")
                            except Exception:
                                text_content = raw_body.decode("utf-8", errors="replace")

                            return FetchResult(
                                url=url,
                                final_url=current_url,
                                status_code=response.status_code,
                                content=text_content,
                                headers=dict(response.headers),
                                content_type=raw_content_type,
                            )
                    except httpx.TimeoutException as exc:
                        raise WebFetchError(f"Bağlantı zaman aşımına uğradı ({self.timeout_seconds}s): {exc}") from exc
                    except httpx.RequestError as exc:
                        raise WebFetchError(f"HTTP isteği başarısız: {exc}") from exc

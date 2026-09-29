"""Web fetch integration with strict SSRF protection, DNS-rebinding IP pinning,
and LinkedIn fetch guard.
"""

from __future__ import annotations

import asyncio
import email.utils
import ipaddress
import logging
import random
import socket
import typing
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend, AnyIOStream

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
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


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


class FetchTimeoutError(WebFetchError):
    """Raised when fetch times out."""


class FetchUnavailableError(WebFetchError):
    """Raised when web fetching repeatedly fails due to server or network issues."""


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content: str
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    etag: str | None = None
    last_modified: str | None = None
    is_not_modified: bool = False


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


def parse_retry_after(header_value: str | None, max_delay: float = 60.0) -> float | None:
    """Parse standard HTTP Retry-After header (seconds or RFC 7231 date)."""
    if not header_value:
        return None
    try:
        val = float(header_value.strip())
        return min(max(0.0, val), max_delay)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(header_value)
        if dt is not None:
            delay = (dt - datetime.now(timezone.utc)).total_seconds()
            return min(max(0.0, delay), max_delay)
    except Exception:
        pass
    return None


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 10.0) -> float:
    """Calculate exponential backoff delay with random jitter."""
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0.0, 0.25)
    return min(cap, exp + jitter)


async def validate_url_for_ssrf(url: str, allowed_ports: set[int] | None = None) -> None:
    """Strictly validate URL structure, scheme, hostname, port, and resolved IP against SSRF."""
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

    # Check port against allowed ports
    configured_ports = allowed_ports if allowed_ports is not None else settings.allowed_fetch_ports
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    if port not in configured_ports:
        raise SSRFProtectionError(
            f"Erişime kapalı bağlantı noktası: {port}. İzin verilenler: {sorted(configured_ports)}"
        )

    # NEVER SCRAPE LINKEDIN!
    if is_linkedin_url(url):
        raise LinkedInFetchForbiddenError(
            f"LinkedIn sayfalarını çekmek kesinlikle yasaktır ({url}). "
            "LinkedIn bağlantıları yalnızca gezinme bağlantısı olarak kullanıcıya sunulur."
        )

    # Resolve hostname via DNS and check all resolved IPs
    loop = asyncio.get_running_loop()
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


class SSRFGuardedBackend(AnyIOBackend):
    """Custom network backend that pins TCP connection directly to a pre-validated IP,
    defeating TOCTOU DNS rebinding while preserving TLS SNI and cert verification.
    """

    def __init__(self, allowed_ports: set[int] | None = None) -> None:
        super().__init__()
        self.allowed_ports = allowed_ports if allowed_ports is not None else settings.allowed_fetch_ports

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore._backends.anyio.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if port not in self.allowed_ports:
            raise SSRFProtectionError(
                f"Erişime kapalı bağlantı noktası: {port}. İzin verilenler: {sorted(self.allowed_ports)}"
            )

        # Check if host is an IP literal
        try:
            ip_obj = ipaddress.ip_address(host)
            if is_ip_prohibited(ip_obj):
                raise SSRFProtectionError(
                    f"Erişimi engellenen özel/dahili IP adresine bağlanılamaz: {host}"
                )
            pinned_ip = str(ip_obj)
        except ValueError:
            # Host is a domain name: resolve DNS and validate all returned IPs
            loop = asyncio.get_running_loop()
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

            # Pin to the first validated IP
            pinned_ip = addr_info[0][4][0]

        return await super().connect_tcp(
            host=pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFGuardedTransport(httpx.AsyncHTTPTransport):
    """Async transport with SSRFGuardedBackend enforcing connection-level IP pinning and port checking."""

    def __init__(self, allowed_ports: set[int] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._backend = SSRFGuardedBackend(allowed_ports=allowed_ports)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._pool._ssl_context,
            max_connections=self._pool._max_connections,
            max_keepalive_connections=self._pool._max_keepalive_connections,
            keepalive_expiry=self._pool._keepalive_expiry,
            http1=self._pool._http1,
            http2=self._pool._http2,
            retries=self._pool._retries,
            network_backend=self._backend,
        )


class SafeWebFetcher:
    """Safe, bounded web fetcher with SSRF guards, DNS-rebinding IP pinning,
    manual redirect validation, size limits, exponential backoff retries,
    conditional caching headers (ETag / Last-Modified), and strict LinkedIn fetch prohibition.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        max_concurrency: int | None = None,
        user_agent: str | None = None,
        retry_max_attempts: int | None = None,
        client: httpx.AsyncClient | None = None,
        sleeper: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds or settings.web_fetch_timeout_seconds
        self.max_bytes = max_bytes or settings.web_fetch_max_bytes
        self.max_redirects = max_redirects or settings.web_fetch_max_redirects
        self.semaphore = asyncio.Semaphore(
            max(1, max_concurrency or settings.web_fetch_max_concurrency)
        )
        self.user_agent = user_agent or settings.web_fetch_user_agent
        self.retry_max_attempts = (
            retry_max_attempts
            if retry_max_attempts is not None
            else settings.web_fetch_retry_max_attempts
        )
        self._custom_client = client
        self._client: httpx.AsyncClient | None = client
        self._sleeper = sleeper
        self.available = True
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client is not None and not self._client.is_closed:
                return self._client
            transport = SSRFGuardedTransport(
                allowed_ports=settings.allowed_fetch_ports,
                verify=True,
            )
            self._client = httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
                timeout=httpx.Timeout(self.timeout_seconds),
                verify=True,
            )
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None and not self._client.is_closed:
                # If it's a client passed externally, don't close it; otherwise close
                if self._client is not self._custom_client:
                    await self._client.aclose()
                self._client = None

    async def __aenter__(self) -> SafeWebFetcher:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Fetch URL content with strict SSRF validation on every redirect hop,
        DNS rebinding defense, byte size enforcement, and bounded retries.
        """
        async with self.semaphore:
            attempt = 0
            while attempt < self.retry_max_attempts:
                attempt += 1
                current_url = url
                hop = 0

                headers = {
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/ld+json;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
                }
                if etag:
                    headers["If-None-Match"] = etag
                if last_modified:
                    headers["If-Modified-Since"] = last_modified

                client = await self._get_client()

                try:
                    while True:
                        await validate_url_for_ssrf(current_url)

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

                            # 304 Not Modified
                            if response.status_code == 304:
                                return FetchResult(
                                    url=url,
                                    final_url=current_url,
                                    status_code=304,
                                    content="",
                                    headers=dict(response.headers),
                                    content_type=response.headers.get("content-type", "").lower(),
                                    etag=response.headers.get("etag") or etag,
                                    last_modified=response.headers.get("last-modified") or last_modified,
                                    is_not_modified=True,
                                )

                            # Transient / retryable HTTP status codes
                            if response.status_code in RETRYABLE_STATUS:
                                if attempt < self.retry_max_attempts:
                                    retry_after = parse_retry_after(response.headers.get("retry-after"))
                                    delay = retry_after if retry_after is not None else backoff_delay(attempt)
                                    logger.warning(
                                        "Web fetch retryable status %d for %s (attempt %d/%d), retrying in %.2fs",
                                        response.status_code, current_url, attempt, self.retry_max_attempts, delay
                                    )
                                    await self._sleeper(delay)
                                    break  # Break inner loop to retry outer attempt
                                else:
                                    raise FetchUnavailableError(
                                        f"HTTP isteği başarısız ({response.status_code}): {current_url}"
                                    )

                            # 404 / 410 (resource not found or gone)
                            if response.status_code in {404, 410}:
                                return FetchResult(
                                    url=url,
                                    final_url=current_url,
                                    status_code=response.status_code,
                                    content="",
                                    headers=dict(response.headers),
                                    content_type=response.headers.get("content-type", "").lower(),
                                    etag=response.headers.get("etag"),
                                    last_modified=response.headers.get("last-modified"),
                                    is_not_modified=False,
                                )

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
                            body_chunks: list[bytes] = []
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
                                etag=response.headers.get("etag"),
                                last_modified=response.headers.get("last-modified"),
                                is_not_modified=False,
                            )

                except (
                    SSRFProtectionError,
                    LinkedInFetchForbiddenError,
                    ResponseTooLargeError,
                    InvalidContentTypeError,
                    TooManyRedirectsError,
                    FetchUnavailableError,
                ):
                    # Do not retry fatal policy, format, or security violations
                    raise
                except httpx.TimeoutException as exc:
                    if attempt < self.retry_max_attempts:
                        delay = backoff_delay(attempt)
                        logger.warning(
                            "Web fetch timeout for %s (attempt %d/%d), retrying in %.2fs",
                            current_url, attempt, self.retry_max_attempts, delay
                        )
                        await self._sleeper(delay)
                        continue
                    raise FetchTimeoutError(
                        f"Bağlantı zaman aşımına uğradı ({self.timeout_seconds}s): {exc}"
                    ) from exc
                except (httpx.RequestError, httpcore.NetworkError, httpcore.TimeoutException) as exc:
                    if attempt < self.retry_max_attempts:
                        delay = backoff_delay(attempt)
                        logger.warning(
                            "Web fetch network error for %s (attempt %d/%d), retrying in %.2fs: %s",
                            current_url, attempt, self.retry_max_attempts, delay, exc
                        )
                        await self._sleeper(delay)
                        continue
                    raise WebFetchError(f"HTTP isteği başarısız: {exc}") from exc

            raise FetchUnavailableError(f"İstek deneme sınırı ({self.retry_max_attempts}) aşıldı: {url}")

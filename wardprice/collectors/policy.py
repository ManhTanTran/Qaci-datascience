"""Permission-gated HTTPS fetcher that fails closed on robots errors and rate limits."""

from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .models import FetchResponse
from .parsing import canonical_url


class CollectionBlocked(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def _non_public_host(host: str) -> bool:
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CollectionBlocked("DNS_ERROR", "Could not resolve source host") from exc
    for record in records:
        address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        if not address.is_global:
            return True
    return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl


def _http_get(url: str, *, timeout: float, headers: dict[str, str]) -> FetchResponse:
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=timeout)
        status = response.status
        response_headers = {key.casefold(): value for key, value in response.headers.items()}
        body = response.read(2_000_000)
        response.close()
    except urllib.error.HTTPError as error:
        status = error.code
        response_headers = {key.casefold(): value for key, value in error.headers.items()}
        body = error.read(64_000)
        error.close()
    return FetchResponse(
        url=url,
        status_code=status,
        headers=response_headers,
        body=body,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        retry_after=response_headers.get("retry-after"),
    )


class RobotsAwareClient:
    def __init__(
        self,
        source: dict,
        *,
        transport: Callable[..., FetchResponse] | None = None,
        timeout_seconds: float = 12,
        min_delay_seconds: float = 1,
        max_page_bytes: int = 2_000_000,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        on_attempt: Callable[[dict], None] | None = None,
        shared_budget: dict[str, int] | None = None,
    ) -> None:
        self.source = source
        self.host = (urlsplit(source["base_url"]).hostname or "").casefold()
        self.domains = [self.host.removeprefix("www.")]
        self.user_agent = source["user_agent"]
        self.timeout_seconds = timeout_seconds
        self.min_delay_seconds = max(min_delay_seconds, float(source.get("crawl_delay_seconds", 0)))
        self.max_page_bytes = max_page_bytes
        self.transport = transport or _http_get
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.on_attempt = on_attempt or (lambda record: None)
        self.shared_budget = shared_budget
        self._robots: RobotFileParser | None = None
        self._last_request: float | None = None
        self._blocked_until: datetime | None = None
        self.requests_made = 0

    def _assert_source_url(self, url: str) -> str:
        canonical = canonical_url(url)
        parsed = urlsplit(canonical)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise CollectionBlocked("UNSAFE_URL", "Source URLs must be credential-free HTTPS URLs")
        if parsed.port not in {None, 443}:
            raise CollectionBlocked("UNSAFE_PORT", "Only the standard HTTPS port is allowed")
        if host != self.host and host.removeprefix("www.") != self.host.removeprefix("www."):
            raise CollectionBlocked("HOST_NOT_ALLOWED", "URL host is outside the configured source")
        return canonical

    def _request(self, url: str, *, purpose: str) -> FetchResponse:
        canonical = self._assert_source_url(url)
        if self._blocked_until and self.now() < self._blocked_until:
            raise CollectionBlocked("RETRY_AFTER", "Source cooldown is active")
        wait = 0.0
        if self._last_request is not None:
            wait = max(0.0, self.min_delay_seconds - (self.monotonic() - self._last_request))
        if wait:
            self.sleeper(wait)
        self._last_request = self.monotonic()
        self.requests_made += 1
        if self.requests_made > int(self.source["daily_request_budget"]):
            raise CollectionBlocked("DAILY_SOURCE_BUDGET", "Source daily request budget exhausted")
        if self.shared_budget is not None:
            if self.shared_budget["remaining"] <= 0:
                self.requests_made -= 1
                raise CollectionBlocked("GLOBAL_DAILY_BUDGET", "Global daily request budget exhausted")
            self.shared_budget["remaining"] -= 1
        try:
            if self.transport is _http_get:
                host = urlsplit(canonical).hostname or ""
                if _non_public_host(host):
                    raise CollectionBlocked("NON_PUBLIC_ADDRESS", "Source resolved to a non-public address")
            response = self.transport(
                canonical,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent, "Accept": "text/html,application/ld+json;q=0.9,*/*;q=0.2"},
            )
        except CollectionBlocked:
            raise
        except Exception as exc:
            self.on_attempt({"url": canonical, "purpose": purpose, "status_code": None, "error": type(exc).__name__})
            raise CollectionBlocked("NETWORK_ERROR", f"Source request failed: {type(exc).__name__}") from exc
        if len(response.body) > self.max_page_bytes:
            raise CollectionBlocked("RESPONSE_TOO_LARGE", "Source response exceeded the configured byte limit")
        self.on_attempt({
            "url": canonical,
            "purpose": purpose,
            "status_code": response.status_code,
            "fetched_at": response.fetched_at,
            "retry_after": response.retry_after,
        })
        if response.status_code == 429 or response.status_code == 403:
            self._set_cooldown(response.retry_after)
            raise CollectionBlocked(
                "HTTP_429" if response.status_code == 429 else "HTTP_403",
                "Source refused automated access; collection stopped without retry",
                retry_after=response.retry_after,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise CollectionBlocked("HTTP_ERROR", f"Source returned HTTP {response.status_code}")
        if purpose != "robots":
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
            if content_type and content_type not in {
                "text/html",
                "application/xhtml+xml",
                "application/ld+json",
                "application/json",
            }:
                raise CollectionBlocked("UNSUPPORTED_CONTENT_TYPE", "Source did not return a listing page")
        return response

    def _set_cooldown(self, value: str | None) -> None:
        now = self.now()
        until = now + timedelta(hours=24)
        if value:
            try:
                until = now + timedelta(seconds=max(0, min(86_400, int(value))))
            except ValueError:
                try:
                    until = parsedate_to_datetime(value).astimezone(timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    pass
        self._blocked_until = until

    def _load_robots(self) -> RobotFileParser:
        if self._robots is not None:
            return self._robots
        robots_url = self._assert_source_url(self.source["robots_url"])
        response = self._request(robots_url, purpose="robots")
        parser = RobotFileParser(robots_url)
        parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
        self._robots = parser
        return parser

    def fetch(self, url: str, *, purpose: str = "page") -> FetchResponse:
        canonical = self._assert_source_url(url)
        robots = self._load_robots()
        if not robots.can_fetch(self.user_agent, canonical):
            raise CollectionBlocked("ROBOTS_DISALLOW", "robots.txt disallows this URL")
        delay = robots.crawl_delay(self.user_agent) or robots.crawl_delay("*") or 0
        self.min_delay_seconds = max(self.min_delay_seconds, float(delay))
        return self._request(canonical, purpose=purpose)

    def health_check(self) -> dict:
        try:
            robots = self._load_robots()
            return {"status": "ROBOTS_READ", "can_fetch_root": robots.can_fetch(self.user_agent, self.source["base_url"]), "network_requests": self.requests_made}
        except CollectionBlocked as exc:
            return {"status": exc.code, "error": str(exc), "network_requests": self.requests_made}

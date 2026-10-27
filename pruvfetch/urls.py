"""Safe URL ingest stub. Validates only; never fetches in mock mode."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

_PRIVATE_SUFFIXES = (".local", ".internal", ".lan", ".invalid")


@dataclass(frozen=True)
class UrlIngestResult:
    url: str
    valid: bool
    fetched: bool = False
    reason: str = ""
    host: str = ""


def _blocked_host(host: str) -> str | None:
    h = host.strip().lower().rstrip(".")
    if not h:
        return "empty host"
    if h in ("localhost", "::1"):
        return "loopback blocked"
    if h.endswith(_PRIVATE_SUFFIXES):
        return "private suffix blocked"
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return None
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return "private/link-local/reserved IP blocked"
    return None


def validate_url(url: str) -> UrlIngestResult:
    """Validate a public http(s) URL. No network I/O; fetched is always False."""
    raw = (url or "").strip()
    if not raw:
        return UrlIngestResult(url=url, valid=False, reason="empty URL")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        return UrlIngestResult(url=url, valid=False, reason=f"unparseable: {exc}")
    if parts.scheme not in ("http", "https"):
        return UrlIngestResult(url=url, valid=False, reason="scheme must be http/https")
    if "@" in parts.netloc:
        return UrlIngestResult(url=url, valid=False, reason="credentialed URLs blocked")
    host = parts.hostname or ""
    blocked = _blocked_host(host)
    if blocked:
        return UrlIngestResult(url=url, valid=False, host=host, reason=blocked)
    return UrlIngestResult(url=raw, valid=True, host=host, reason="ok (not fetched)")


def ingest_url(url: str, allow_network: bool = False) -> UrlIngestResult:
    """Mock ingest: validate only. Live fetch is disabled in Phase 1."""
    if allow_network:
        raise RuntimeError("live fetch disabled in Phase 1 mock")
    return validate_url(url)

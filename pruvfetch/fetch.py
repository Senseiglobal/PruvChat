"""Safe public-URL retrieval. HTTP(S) only, SSRF guards, size/time caps.

Every hop (initial URL plus each redirect) is re-validated: scheme, host
blocklist, port allowlist, and DNS resolution to public IPs only.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pruvfetch.extract import extract_text
from pruvfetch.urls import validate_url

FETCH_TIMEOUT = 10
FETCH_MAX_BYTES = 500_000
FETCH_MAX_REDIRECTS = 3
ALLOWED_PORTS = {80, 443}
TEXT_TYPES = ("text/plain", "text/markdown", "text/csv", "application/json")


class _Redirected(Exception):
    """Raised instead of following a redirect; carries code + Location."""

    def __init__(self, code: int, location: str):
        super().__init__(f"HTTP {code}")
        self.code = code
        self.location = location or ""


class _ManualRedirect(HTTPRedirectHandler):
    """Never auto-follow; surface redirects so each hop is re-validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(code, newurl or "")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html[:FETCH_MAX_BYTES])
    return "\n".join(parser.parts)


@dataclass(frozen=True)
class FetchedDoc:
    url: str
    final_url: str = ""
    status: int = 0
    content_type: str = ""
    text: str = ""
    size_bytes: int = 0
    truncated: bool = False
    fetched_at: str = ""
    warning: str = ""


def _fail(url: str, warning: str) -> FetchedDoc:
    return FetchedDoc(url=url, warning=warning)


def _dns_public_ips(host: str, port: int) -> tuple | str:
    """Resolve host; return tuple of IP strings or an error message."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "DNS resolution failed"
    ips = []
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            return f"unparseable resolved IP for {host}"
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return f"host resolves to non-public IP ({ip})"
        ips.append(ip)
    if not ips:
        return "DNS returned no addresses"
    return tuple(ips)


def _check_hop(raw: str) -> str | None:
    """Validate one redirect hop. Returns error message or None."""
    result = validate_url(raw)
    if not result.valid:
        return result.reason
    parts = urlsplit(result.url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return f"port {port} not allowed (80/443 only)"
    dns = _dns_public_ips(parts.hostname or "", port)
    if isinstance(dns, str):
        return dns
    return None


def fetch_url(url: str, timeout: int = FETCH_TIMEOUT) -> FetchedDoc:
    """Fetch a public document with SSRF guards. Never raises on fetch errors."""
    raw = (url or "").strip()
    problem = _check_hop(raw)
    if problem:
        return _fail(url, problem)
    opener = build_opener(_ManualRedirect())
    opener.addheaders = [("User-Agent", "PruvChat/0.1 (evidence research; +local)")]
    current = validate_url(raw).url
    try:
        for _ in range(FETCH_MAX_REDIRECTS + 1):
            req = Request(current, headers={"Accept": "text/*,application/json,application/pdf,*/*;q=0.1"})
            try:
                resp = opener.open(req, timeout=timeout)
            except _Redirected as red:
                nxt = urljoin(current, red.location) if red.location else ""
                hop_problem = _check_hop(nxt) if nxt else "redirect without Location"
                if hop_problem:
                    return _fail(url, f"redirect blocked: {hop_problem}")
                current = validate_url(nxt).url
                continue
            except Exception as exc:
                return _fail(url, f"request failed: {type(exc).__name__}")
            status = getattr(resp, "status", 200) or 200
            if status in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                nxt = urljoin(current, location) if location else ""
                hop_problem = _check_hop(nxt) if nxt else "redirect without Location"
                if hop_problem:
                    return _fail(url, f"redirect blocked: {hop_problem}")
                current = validate_url(nxt).url
                continue
            if status != 200:
                return _fail(url, f"HTTP {status}")
            ctype = (resp.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
            chunks: list = []
            remaining = FETCH_MAX_BYTES + 1
            while remaining > 0:
                piece = resp.read(min(65536, remaining))
                if not piece:
                    break
                chunks.append(piece)
                remaining -= len(piece)
            data = b"".join(chunks)
            truncated = len(data) > FETCH_MAX_BYTES
            data = data[:FETCH_MAX_BYTES]
            stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
            if ctype == "text/html":
                text = html_to_text(data.decode("utf-8", errors="replace"))
                return FetchedDoc(url=url, final_url=current, status=status, content_type=ctype,
                                  text=text, size_bytes=len(data), truncated=truncated, fetched_at=stamp)
            if ctype in TEXT_TYPES or ctype.startswith("text/"):
                return FetchedDoc(url=url, final_url=current, status=status, content_type=ctype,
                                  text=data.decode("utf-8", errors="replace"), size_bytes=len(data),
                                  truncated=truncated, fetched_at=stamp)
            if ctype == "application/pdf":
                ext = extract_text(current, data)
                warn = ext.warning or ("truncated at fetch cap" if truncated else "")
                return FetchedDoc(url=url, final_url=current, status=status, content_type=ctype,
                                  text=ext.text, size_bytes=len(data), truncated=truncated,
                                  fetched_at=stamp, warning=warn)
            return _fail(url, f"unsupported content type: {ctype or 'unknown'}")
        return _fail(url, "too many redirects")
    except Exception as exc:  # never let user input crash the caller
        return _fail(url, f"fetch failed: {type(exc).__name__}")

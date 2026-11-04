"""Official government source retrieval for visa readiness reviews.

Single page fetches started by the user. No crawling, no scheduler, no
background refresh. Every fetch uses the guarded pipeline (scheme, host,
and DNS checks, redirect revalidation, size and time caps). Applicant
documents never leave this machine: requests are plain GETs for the
official URL only, with no document content attached.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import re as _re
import time as _time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from pruvfetch.fetch import fetch_url
from pruvfetch.urls import validate_url

OFFICIAL_DOMAINS = ("gov.uk", "uscis.gov", "canada.ca", "homeaffairs.gov.au",
                    "france-visas.gouv.fr", "auswaertiges-amt.de", "mofa.go.jp")
PUBLISHERS = {"gov.uk": "GOV.UK", "uscis.gov": "USCIS",
              "canada.ca": "Government of Canada",
              "homeaffairs.gov.au": "Australia Home Affairs",
              "france-visas.gouv.fr": "France-Visas",
              "auswaertiges-amt.de": "German Federal Foreign Office",
              "mofa.go.jp": "Japan MOFA"}
# Official immigration portals per quick destination. Shown as outbound links
# for routes without a verified checklist. Not live verified in this sprint.
COUNTRY_PORTALS = {
    "United Kingdom": {"name": "GOV.UK", "url": "https://www.gov.uk"},
    "United States": {"name": "USCIS", "url": "https://www.uscis.gov"},
    "Canada": {"name": "Canada immigration", "url": "https://www.canada.ca/en/immigration-refugees-citizenship.html"},
    "Australia": {"name": "Australia Home Affairs", "url": "https://immi.homeaffairs.gov.au"},
    "Germany": {"name": "German Federal Foreign Office", "url": "https://www.auswaertiges-amt.de/en"},
    "France": {"name": "France-Visas", "url": "https://france-visas.gouv.fr"},
    "Japan": {"name": "Japan MOFA", "url": "https://www.mofa.go.jp"},
}
# Preset addresses are suggestions only: the UI asks the user to confirm the
# address before fetching, and a wrong address fails honestly. These slugs
# were not live verified in this sprint.
PRESET_ROUTES = (
    {"label": "UK Standard Visitor visa",
     "url": "https://www.gov.uk/standard-visitor-visa",
     "note": "Visitor rules change often. Confirm the address above opens the current official page before fetching."},
    {"label": "UK Global Talent visa",
     "url": "https://www.gov.uk/global-talent",
     "note": "Global Talent has more than one pathway, including endorsement and prize routes. Each pathway has its own steps. Confirm your pathway on the official page before using these items."},
    {"label": "UK Skilled Worker visa",
     "url": "https://www.gov.uk/skilled-worker-visa",
     "note": "Skilled Worker rules depend on your job and sponsor. Confirm the page covers your situation."},
    {"label": "UK Student visa",
     "url": "https://www.gov.uk/student-visa",
     "note": "Student rules differ by course and age. Confirm the page covers your situation."},
    {"label": "UK Family visa",
     "url": "https://www.gov.uk/uk-family-visa",
     "note": "Family routes differ by relationship. Confirm the page covers your situation."},
)
ROBOT_AGENT = "PruvChat"
RATE_MIN_SECONDS = 10.0
MAX_CANDIDATES = 12
MAX_CANDIDATE_CHARS = 300
MIN_CANDIDATE_CHARS = 20
MAX_EXCERPT_CHARS = 600
SOURCE_KEY_PREFIX = "official_src_"

_BULLET = _re.compile(r"^\s*(?:[\u2022\-\*]|\d{1,3}[.\)\]])\s+")
_WS = _re.compile(r"\s+")
_SKIP_LINES = frozenset({"cookies", "cookie policy", "privacy notice", "privacy policy",
                         "sign in", "log in", "menu", "search", "subscribe",
                         "terms and conditions", "accessibility statement"})
# Boilerplate phrases: a line containing one is navigation, cookie, or footer
# content, not a requirement. Kept to phrases that never carry requirements.
_BLOCK_CONTAINS = ("cookie", "cookies", "privacy", "subscribe", "newsletter",
                   "all rights reserved", "back to top", "skip to", "sign in",
                   "log in", "follow us", "share this", "print this",
                   "get emails", "related content", "give feedback",
                   "terms and conditions", "accessibility", "copyright", "©")
# Wording cues only: these tag how a line READS, never what the law demands.
_REQ_CUES = ("must", "required", "require", "mandatory", "need to", "needs to",
             "have to", "has to", "will need")
_GUIDE_CUES = ("may", "can", "could", "consider", "usually", "normally",
               "optional", "might", "if you want")
_REQ_CUE_RE = _re.compile(r"\b(" + "|".join(_REQ_CUES) + r")\b")
_GUIDE_CUE_RE = _re.compile(r"\b(" + "|".join(_GUIDE_CUES) + r")\b")
_ALNUM = _re.compile(r"[^a-z0-9]+")


def _domain_of(host: str) -> str:
    h = (host or "").strip().lower().rstrip(".")
    for dom in OFFICIAL_DOMAINS:
        if h == dom or h.endswith("." + dom):
            return dom
    return ""


def is_official_url(url: str) -> tuple:
    """(ok, reason, domain). Unsafe or off-allowlist URLs fail closed."""
    result = validate_url(url)
    if not result.valid:
        return False, result.reason, ""
    dom = _domain_of(result.host)
    if not dom:
        return False, f"host {result.host} is not on the official domain list", ""
    return True, "ok", dom


def robots_url_for(url: str) -> str:
    """robots.txt address for a validated URL. Raises ValueError when invalid."""
    result = validate_url(url)
    if not result.valid:
        raise ValueError(result.reason)
    parts = urlsplit(result.url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def robots_verdict(robots_text: str, path: str, agent: str = ROBOT_AGENT) -> str:
    """allowed, disallowed, or unavailable (empty or unparseable body). Pure."""
    if not (robots_text or "").strip():
        return "unavailable"
    parser = RobotFileParser()
    try:
        parser.parse((robots_text or "").splitlines())
    except Exception:
        return "unavailable"
    try:
        return "allowed" if parser.can_fetch(agent, path or "/") else "disallowed"
    except Exception:
        return "unavailable"


def normalize_text(text: str) -> str:
    """Collapse whitespace for stable hashing and comparison. Pure."""
    return _WS.sub(" ", text or "").strip()


def content_hash(text: str) -> str:
    """SHA-256 hex of the normalized text. Pure."""
    return _hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def source_id_for(final_url: str) -> str:
    """Stable 12-char id from the normalized final URL. Pure."""
    clean = (final_url or "").strip().lower().rstrip("/")
    return _hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]


def rate_allowed(fetch_times: dict, key: str, now: float,
                 min_seconds: float = RATE_MIN_SECONDS) -> tuple:
    """(allowed, wait_seconds). Pure over the caller-owned timestamps dict."""
    try:
        last = float((fetch_times or {}).get(key, 0.0))
    except (TypeError, ValueError):
        last = 0.0
    wait = min_seconds - (now - last)
    if wait <= 0:
        return True, 0.0
    return False, round(wait, 1)


def _friendly_reason(warning: str) -> str:
    low = (warning or "").lower()
    if "401" in low:
        return "page needs login (HTTP 401), so it cannot be read here"
    if "403" in low:
        return "page blocked this read (HTTP 403); it may need login or block automated reads"
    if "404" in low:
        return "page not found (HTTP 404); the address may have moved"
    return warning or "fetch failed"


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _error_record(url: str, reason: str, route: str = "") -> dict:
    return {"id": source_id_for(url), "route": route, "url": (url or "").strip(),
            "final_url": "", "publisher": "", "title": "", "retrieved_at": _stamp(),
            "published": "", "excerpt": "", "text_hash": "", "status": "error",
            "reason": reason, "robots": "unavailable", "content_type": "",
            "http_status": 0, "note": "", "full_text": ""}


def build_source_record(url: str, doc, route: str = "", robots: str = "allowed",
                        retrieved_at: str | None = None) -> dict:
    """Source record from a fetched document. Honest about missing fields.

    Empty dates stay empty (shown as not available); failed fetches become
    error records. Never invents content.
    """
    stamp = retrieved_at or _stamp()
    if doc is None or (getattr(doc, "warning", "") and not getattr(doc, "text", "")):
        warning = getattr(doc, "warning", "") if doc is not None else ""
        rec = _error_record(url, _friendly_reason(warning), route)
        rec["retrieved_at"] = stamp
        return rec
    final_url = getattr(doc, "final_url", "") or ""
    host = urlsplit(final_url).hostname or ""
    text = getattr(doc, "text", "") or ""
    return {"id": source_id_for(final_url or url), "route": route,
            "url": (url or "").strip(), "final_url": final_url,
            "publisher": PUBLISHERS.get(_domain_of(host), host),
            "title": (getattr(doc, "title", "") or "")[:200],
            "retrieved_at": stamp, "published": getattr(doc, "published", "") or "",
            "excerpt": text.strip()[:MAX_EXCERPT_CHARS],
            "text_hash": content_hash(text), "status": "retrieved", "reason": "",
            "robots": robots, "content_type": getattr(doc, "content_type", "") or "",
            "http_status": getattr(doc, "status", 0) or 0,
            "note": (getattr(doc, "warning", "") or "")[:200], "full_text": text}


def request_source(url: str, route: str = "", fetch_times: dict | None = None,
                   now: float | None = None) -> dict:
    """One user-triggered official fetch. Returns a record, never raises on faults.

    Runs the allowlist, rate limit, robots check, then the guarded fetch.
    fetch_times is caller-owned (session state in the app); None skips the
    rate limit. Only successful main fetches stamp the rate limiter.
    """
    moment = now if now is not None else _time.time()
    ok, reason, _ = is_official_url(url)
    if not ok:
        return _error_record(url, reason, route)
    key = (url or "").strip().lower()
    if fetch_times is not None:
        allowed, wait = rate_allowed(fetch_times, key, moment)
        if not allowed:
            return _error_record(
                url, f"rate limited: please wait {wait:g} seconds, then try again", route)
    try:
        robots_doc = fetch_url(robots_url_for(url))
        robots_text = robots_doc.text if robots_doc and not robots_doc.warning else ""
    except Exception:
        robots_text = ""
    path = urlsplit(validate_url(url).url).path or "/"
    robots = robots_verdict(robots_text, path)
    if robots == "disallowed":
        return _error_record(url, "blocked by the site robots file", route)
    try:
        doc = fetch_url(url)
    except Exception as exc:
        return _error_record(url, f"request failed: {type(exc).__name__}", route)
    if fetch_times is not None:
        fetch_times[key] = moment
    return build_source_record(url, doc, route, robots=robots)


def _wording_hint(low: str) -> str:
    """Tag how a line reads from wording cues only. Ambiguous lines stay unclassified."""
    req = bool(_REQ_CUE_RE.search(low))
    guide = bool(_GUIDE_CUE_RE.search(low))
    if req and not guide:
        return "wording suggests a requirement"
    if guide and not req:
        return "wording suggests guidance"
    return "not classified"


def extract_candidates(text: str, source_id: str, source_url: str,
                       max_items: int = MAX_CANDIDATES) -> list:
    """Verbatim candidate lines from source text. No invention, no legal reading.

    Drops navigation, cookie, and footer lines, collapses near-duplicates, and
    tags wording cues. Each candidate carries its exact excerpt plus the
    source link. Every candidate needs human review. Pure function.
    """
    out: list = []
    seen: set = set()
    for raw in (text or "").splitlines():
        if len(out) >= max_items:
            break
        excerpt = (raw or "").strip()
        cleaned = _BULLET.sub("", excerpt).strip()
        if len(cleaned) < MIN_CANDIDATE_CHARS:
            continue
        low = cleaned.lower()
        if (low in _SKIP_LINES or low.startswith(("http://", "https://", "www."))
                or low.startswith("home >") or "›" in low
                or any(phrase in low for phrase in _BLOCK_CONTAINS)):
            continue
        key = _ALNUM.sub("", low)
        if not key or any(key in kept for kept in seen):
            continue
        seen.add(key)
        out.append({"text": cleaned[:MAX_CANDIDATE_CHARS],
                    "excerpt": excerpt[:MAX_CANDIDATE_CHARS],
                    "source_id": source_id, "source_url": source_url,
                    "status": "Needs human review",
                    "classification": _wording_hint(low)})
    return out


def refresh_state(old_hash: str, new_hash: str) -> str:
    """Changed or Unchanged for two stored content hashes. Pure."""
    if old_hash and new_hash and old_hash == new_hash:
        return "Unchanged"
    return "Changed"


def pack_sources(records: list) -> dict:
    """Compact records as save-ready string entries (each well under caps). Pure."""
    packed = {}
    for i, rec in enumerate(records or []):
        if not isinstance(rec, dict):
            continue
        slim = {k: rec.get(k, "") for k in ("id", "route", "url", "final_url", "publisher",
                                            "retrieved_at", "published", "text_hash", "status",
                                            "reason", "robots", "content_type", "note")}
        slim["title"] = str(rec.get("title", ""))[:200]
        slim["excerpt"] = str(rec.get("excerpt", ""))[:MAX_EXCERPT_CHARS]
        slim["http_status"] = rec.get("http_status", 0)
        packed[f"{SOURCE_KEY_PREFIX}{i + 1}"] = _json.dumps(slim, ensure_ascii=False)
    return packed


def unpack_sources(inputs: dict) -> list:
    """Restore packed records. Skips corrupt entries, never invents. Pure."""
    found = []
    for key in sorted(inputs or {}):
        if not key.startswith(SOURCE_KEY_PREFIX):
            continue
        try:
            rec = _json.loads(inputs[key])
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict) and rec.get("url"):
            found.append(rec)
    return found

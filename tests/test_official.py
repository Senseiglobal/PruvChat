"""Official government sources: allowlist, records, candidates, refresh. All offline."""
import os

from pruvfetch.fetch import FetchedDoc, html_to_text, page_meta
from pruvfetch.official import (build_source_record, content_hash,
                                extract_candidates, is_official_url,
                                normalize_text, pack_sources, refresh_state,
                                request_source, robots_verdict,
                                source_id_for, unpack_sources)

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
_URL = "https://www.gov.uk/standard-visitor-visa"


def _html(name):
    with open(os.path.join(_FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _doc(text, url=_URL, title="T", published="2026-01-15", warning=""):
    return FetchedDoc(url=url, final_url=url, status=200, content_type="text/html",
                       text=text, size_bytes=len(text), fetched_at="2026-10-29T00:00:00+00:00",
                       title=title, published=published, warning=warning)


def _fake_fetch(page_text, page_warning=""):
    calls = []

    def _fetch(url, timeout=10):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchedDoc(url=url, warning="HTTP 404")
        if page_warning:
            return FetchedDoc(url=url, warning=page_warning)
        return _doc(page_text, url=url, title="Standard Visitor visa rules (SYNTHETIC TEST PAGE)")

    _fetch.calls = calls
    return _fetch


def test_allowlist_accepts_official_hosts_and_subdomains():
    for url in ("https://www.gov.uk/standard-visitor-visa",
                "https://gov.uk/guidance/x",
                "https://deep.host.uscis.gov/form",
                "https://www.canada.ca/en/immigration/x",
                "https://immi.homeaffairs.gov.au/visas/getting-a-visa",
                "https://france-visas.gouv.fr/en/votre-arrivee",
                "https://www.auswaertiges-amt.de/en/visa-service",
                "https://www.mofa.go.jp/j_info/visit/visa/"):
        ok, reason, dom = is_official_url(url)
        assert (ok, reason) == (True, "ok") and dom, url


def test_html_parse_skips_chrome_elements():
    text = html_to_text(_html("official_noisy.html"))
    for gone in ("Back to top", "©", "All rights reserved", "Menu Search Sign in",
                 "Follow us"):
        assert gone not in text
    assert "›" in text  # breadcrumb survives parsing, dies in extraction
    assert "You must send your current passport" in text  # article kept


def test_portals_use_official_domains():
    from pruvfetch.official import COUNTRY_PORTALS, PUBLISHERS

    assert len(COUNTRY_PORTALS) == 7
    for country, portal in COUNTRY_PORTALS.items():
        ok, _, dom = is_official_url(portal["url"])
        assert ok, (country, portal)
        assert dom in PUBLISHERS


def test_allowlist_rejects_unsafe_and_off_domain_urls():
    bad = ["https://example.com/visa", "https://gov.uk.evil.com/x",
           "http://127.0.0.1/secret", "https://localhost/x",
           "https://user:pass@www.gov.uk/", "ftp://www.gov.uk/x", "", "notaurl"]
    for url in bad:
        ok, reason, dom = is_official_url(url)
        assert ok is False and reason and dom == "", url


def test_request_source_blocks_off_allowlist_without_network(monkeypatch):
    def _boom(url, timeout=10):
        raise AssertionError("no network for off-allowlist URLs")

    monkeypatch.setattr("pruvfetch.official.fetch_url", _boom)
    rec = request_source("https://example.com/visa", "Custom official URL")
    assert rec["status"] == "error" and "official domain list" in rec["reason"]
    assert rec["text_hash"] == "" and rec["excerpt"] == ""


def test_request_source_records_metadata(monkeypatch):
    text = html_to_text(_html("official_sample.html"))
    fake = _fake_fetch(text)
    monkeypatch.setattr("pruvfetch.official.fetch_url", fake)
    rec = request_source(_URL, "UK Standard Visitor visa", fetch_times={}, now=1000.0)
    assert rec["status"] == "retrieved"
    assert rec["publisher"] == "GOV.UK" and rec["route"] == "UK Standard Visitor visa"
    assert rec["url"] == _URL and rec["final_url"] == _URL
    assert rec["title"] and "SYNTHETIC" in rec["title"]
    assert rec["published"] == "2026-01-15" and rec["retrieved_at"]
    assert rec["text_hash"] == content_hash(text) and rec["excerpt"]
    assert len(rec["id"]) == 12
    assert fake.calls and all("Alpha beta" not in c for c in fake.calls)  # URL only, no docs


def test_request_source_respects_robots_disallow(monkeypatch):
    calls = []

    def _fetch(url, timeout=10):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchedDoc(url=url, text="User-agent: *\nDisallow: /")
        raise AssertionError("disallowed page must not be fetched")

    monkeypatch.setattr("pruvfetch.official.fetch_url", _fetch)
    rec = request_source(_URL, fetch_times={}, now=1000.0)
    assert rec["status"] == "error" and rec["reason"] == "blocked by the site robots file"
    assert robots_verdict("User-agent: *\nDisallow:", "/x") == "allowed"
    assert robots_verdict("", "/x") == "unavailable"


def test_rate_limit_blocks_fast_repeat(monkeypatch):
    fake = _fake_fetch("Some official text lines for the test page body.")
    monkeypatch.setattr("pruvfetch.official.fetch_url", fake)
    times = {_URL.lower(): 100.0}
    rec = request_source(_URL, now=105.0, fetch_times=times)
    assert rec["status"] == "error" and "wait 5 seconds" in rec["reason"]
    assert fake.calls == []
    rec = request_source(_URL, now=111.0, fetch_times=times)
    assert rec["status"] == "retrieved" and times[_URL.lower()] == 111.0


def test_candidates_are_verbatim_and_flagged():
    text = html_to_text(_html("official_sample.html"))
    first = extract_candidates(text, "abc123", _URL)
    assert 1 <= len(first) <= 12
    for cand in first:
        assert cand["excerpt"] in text  # exact source words, never invented
        assert cand["source_url"] == _URL and cand["source_id"] == "abc123"
        assert cand["status"] == "Needs human review"
        assert cand["classification"] in ("wording suggests a requirement",
                                          "wording suggests guidance",
                                          "not classified")
    tags = {c["text"]: c["classification"] for c in first}
    assert tags["You must hold a passport that stays valid for your whole visit."] == \
        "wording suggests a requirement"
    assert tags["If you visit family, you may need a letter of invitation."] == \
        "wording suggests guidance"
    assert extract_candidates(text, "abc123", _URL) == first  # deterministic
    assert extract_candidates("", "abc123", _URL) == []


def test_extraction_drops_boilerplate_and_duplicates():
    text = html_to_text(_html("official_noisy.html"))
    found = extract_candidates(text, "n1", _URL)
    joined = " ".join(c["text"] for c in found)
    for junk in ("cookie", "Cookies", "©", "›", "Home", "Follow us", "Back to top",
                 "rights reserved", "Privacy", "Menu Search"):
        assert junk not in joined, junk
    assert "You must send your current passport with your application." in joined
    assert "You can track your application online after you apply." in joined
    assert len([c for c in found if "passport" in c["text"]]) == 1  # near-dupe collapsed
    assert len(found) == 4  # title, heading, one requirement, one guidance line


def test_preset_routes_cover_supported_visas():
    from pruvfetch.official import PRESET_ROUTES

    labels = [r["label"] for r in PRESET_ROUTES]
    assert labels[0] == "UK Standard Visitor visa"  # default unchanged
    assert "UK Global Talent visa" in labels  # prominent, not default
    assert len(labels) == 5
    for route in PRESET_ROUTES:
        ok, _, dom = is_official_url(route["url"])
        assert ok and dom == "gov.uk", route
        assert route["note"] and "Confirm" in route["note"]


def test_change_detection_compares_hashes():
    old = content_hash(html_to_text(_html("official_sample.html")))
    new = content_hash(html_to_text(_html("official_sample_changed.html")))
    assert old != new
    assert refresh_state(old, old) == "Unchanged"
    assert refresh_state(old, new) == "Changed"
    assert refresh_state("", new) == "Changed"


def test_pack_unpack_round_trip_and_size():
    rec = build_source_record(_URL, _doc(html_to_text(_html("official_sample.html"))),
                              "UK Standard Visitor visa", retrieved_at="2026-10-29T00:00:00+00:00")
    packed = pack_sources([rec, "junk"])
    assert list(packed) == ["official_src_1"]
    assert all(isinstance(v, str) and len(v) < 2000 for v in packed.values())
    assert "full_text" not in packed["official_src_1"]
    (restored,) = unpack_sources({**packed, "official_src_9": "{bad json"})
    assert restored["url"] == _URL and restored["text_hash"] == rec["text_hash"]
    assert unpack_sources({}) == []


def test_error_record_never_invents_content():
    rec = build_source_record(_URL, FetchedDoc(url=_URL, warning="HTTP 403"))
    assert rec["status"] == "error" and rec["text_hash"] == "" and rec["excerpt"] == ""
    assert "403" in rec["reason"]
    assert normalize_text("  A  B\nC ") == "A B C"


def test_page_meta_reads_title_and_dates_only_when_present():
    meta = page_meta(_html("official_sample.html"))
    assert "SYNTHETIC" in meta["title"] and meta["published"] == "2026-01-15"
    assert page_meta("<p>no head here</p>") == {"title": "", "published": ""}
    assert source_id_for("https://X.gov.uk/a/") == source_id_for("https://x.gov.uk/a")
    assert source_id_for("https://x.gov.uk/a") != source_id_for("https://x.gov.uk/b")

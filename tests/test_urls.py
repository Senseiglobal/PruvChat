"""Safe URL ingest: validation only, private targets blocked, never fetched."""
import pytest

from pruvfetch.urls import ingest_url, validate_url


def test_valid_public_url_passes_but_never_fetched():
    r = validate_url("https://example.com/spec")
    assert r.valid is True
    assert r.fetched is False
    assert r.host == "example.com"


def test_bad_scheme_empty_and_credentialed_rejected():
    assert validate_url("ftp://example.com/x").valid is False
    assert validate_url("").valid is False
    assert validate_url("https://user:pass@example.com/").valid is False


def test_private_targets_blocked():
    for url in ("http://localhost:8000/x", "http://127.0.0.1/", "http://10.0.0.5/",
                "http://192.168.1.1/", "http://172.16.0.9/", "http://printer.local/"):
        assert validate_url(url).valid is False, url


def test_ingest_never_fetches_and_live_flag_refused():
    assert ingest_url("https://example.com/spec").fetched is False
    with pytest.raises(RuntimeError):
        ingest_url("https://example.com/spec", allow_network=True)

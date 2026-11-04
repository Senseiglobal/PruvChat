"""HTTP error mapping and lenient success parsing. Transport fully stubbed."""
import io
import json
from urllib.error import HTTPError

import pytest

import providers.meta_live as live
from providers.meta_live import MetaConfig, MetaLiveProvider, ProviderError

_KEY = "k-secret-xyz"


def _provider(**kwargs):
    return MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": _KEY}), **kwargs)


def _http_error(code, envelope=None):
    body = json.dumps(envelope).encode() if envelope is not None else b""
    return HTTPError("https://api.meta.ai/v1/chat/completions", code, "err", {}, io.BytesIO(body))


def _raise(exc):
    def stub(*a, **k):
        raise exc
    return stub


def _resp(payload: dict):
    body = json.dumps(payload).encode()
    class FakeResp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return FakeResp(body)


def _ok_choices(content, usage=None):
    return {"choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 5, "completion_tokens": 2}}


def _verdict_json(**kw):
    base = {"verdict": "supported", "rationale": "ok", "cited": [0]}
    base.update(kw)
    return json.dumps(base)


def test_401_maps_to_auth_error_without_key(monkeypatch):
    err = _http_error(401, {"error": {"message": "Unauthorized", "type": "authentication_error",
                                      "code": "invalid_api_key"}})
    monkeypatch.setattr(live, "urlopen", _raise(err))
    with pytest.raises(ProviderError) as ei:
        _provider().generate("hello")
    assert "authentication failed (HTTP 401)" in str(ei.value)
    assert "invalid_api_key" in str(ei.value) and _KEY not in str(ei.value)


def test_402_403_404_429_500_mapping(monkeypatch):
    cases = [
        (402, {"error": {"message": "Billing account issue", "type": "billing_error",
                         "code": "billing_not_configured"}}, "billing restriction (HTTP 402)"),
        (403, {"error": {"message": "Denied", "type": "permission_error", "code": "forbidden"}},
         "permission denied (HTTP 403)"),
        (404, None, "not found (HTTP 404)"),
        (429, {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error",
                         "code": "rate_limited"}}, "rate limited (HTTP 429)"),
        (500, None, "server error (HTTP 500)"),
        (418, None, "Meta API error (HTTP 418)"),
    ]
    for code, envelope, needle in cases:
        monkeypatch.setattr(live, "urlopen", _raise(_http_error(code, envelope)))
        with pytest.raises(ProviderError) as ei:
            _provider().generate("hello")
        assert needle in str(ei.value), code
        assert _KEY not in str(ei.value)


def test_network_failure_keeps_generic_type_only(monkeypatch):
    monkeypatch.setattr(live, "urlopen", _raise(TimeoutError("slow")))
    with pytest.raises(ProviderError, match="request failed: TimeoutError"):
        _provider().generate("hello")


def test_non_json_body_reports_status(monkeypatch):
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _raw(b"<html>"))
    with pytest.raises(ProviderError, match="non-JSON body"):
        _provider().generate("hello")


def _raw(body: bytes):
    class FakeResp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return FakeResp(body)


def test_content_blocks_and_alt_usage_parsed(monkeypatch):
    content = [{"type": "text", "text": _verdict_json()}, {"type": "image", "src": "x"}]
    payload = _ok_choices(content, {"input_tokens": 7, "output_tokens": 3})
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
    p = _provider()
    out = p.assess_claim("c?", ["evidence one"])
    assert out["verdict"] == "supported" and out["cited"] == (0,)
    assert p.usage_total == {"input_tokens": 7, "output_tokens": 3}


def test_shape_failures_name_field_not_content(monkeypatch):
    cases = [
        ({"nope": 1}, "missing choices\\[0\\]"),
        ({"choices": []}, "missing choices\\[0\\]"),
        ({"choices": [{"message": {"content": None}}]}, "content is null"),
        ({"choices": [{"message": {"content": 42}}]}, "content has type int"),
        ({"choices": [{"message": {"content": [{"type": "image"}]}}]}, "no text"),
        ({"choices": [{"message": {"content": "not json{"}}]}, "unparseable JSON content"),
    ]
    for payload, pattern in cases:
        monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
        with pytest.raises(ProviderError, match=pattern):
            _provider().assess_claim("c?", ["e"])

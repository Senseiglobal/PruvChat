"""Safe response diagnostics: structure without secrets or content. All stubbed."""
import io
import json

import pytest

import providers.meta_live as live
from providers.meta_live import (
    MAX_OUTPUT_TOKENS,
    REASONING_EFFORT,
    MetaConfig,
    MetaLiveProvider,
    ProviderError,
)

_KEY = "k-secret-xyz"


def _provider(**kwargs):
    return MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": _KEY}), **kwargs)


def _resp(payload: dict):
    body = json.dumps(payload).encode()
    class FakeResp(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return FakeResp(body)


def _choice(message, finish="stop", usage=None):
    return {"choices": [{"message": message, "finish_reason": finish, "index": 0}],
            "usage": usage or {"prompt_tokens": 9, "completion_tokens": 4}}


def test_refusal_raises_with_indicators_not_verdict(monkeypatch):
    payload = _choice({"role": "assistant", "content": None,
                       "refusal": "I cannot help with that request."}, finish="stop")
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
    p = _provider()
    with pytest.raises(ProviderError, match="refused by model"):
        p.assess_claim("c?", ["e"])
    assert p.calls == []
    d = p.last_diagnostics
    assert d["refusal_present"] is True and d["finish_reason"] == "stop"
    assert "refusal" in d["message_keys"] and d["http_status"] == 200
    dumped = json.dumps(d)
    assert _KEY not in dumped and "cannot help" not in dumped


def test_bare_null_reports_structure(monkeypatch):
    payload = _choice({"role": "assistant", "content": None, "reasoning_content": "hmm"},
                      finish="stop", usage={"prompt_tokens": 9, "completion_tokens": 0})
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
    p = _provider()
    with pytest.raises(ProviderError, match="content is null"):
        p.assess_claim("c?", ["e"])
    d = p.last_diagnostics
    assert d["finish_reason"] == "stop" and "reasoning_content" in d["message_keys"]
    assert d["usage"] == {"input_tokens": 9, "output_tokens": 0}
    assert d["refusal_present"] is False
    assert _KEY not in json.dumps(d)


def test_length_truncation_names_budget_not_verdict(monkeypatch):
    payload = _choice({"role": "assistant", "content": None}, finish="length",
                      usage={"prompt_tokens": 167, "completion_tokens": 300,
                             "reasoning_tokens": 290})
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
    p = _provider()
    with pytest.raises(ProviderError, match="truncated by output-token budget"):
        p.assess_claim("c?", ["e"])
    assert p.calls == []
    d = p.last_diagnostics
    assert d["finish_reason"] == "length" and d["reasoning_tokens"] == 290
    assert d["usage"] == {"input_tokens": 167, "output_tokens": 300}
    assert _KEY not in json.dumps(d)


def test_success_records_safe_diagnostics(monkeypatch):
    content = json.dumps({"verdict": "supported", "rationale": "Sky matches", "cited": [0]})
    payload = _choice({"role": "assistant", "content": content})
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(payload))
    p = _provider()
    p.assess_claim("The sky is blue?", ["Sky appears blue at noon."])
    d = p.last_diagnostics
    assert d["http_status"] == 200 and d["finish_reason"] == "stop"
    assert d["content_chars"] == len(content) and d["refusal_present"] is False
    dumped = json.dumps(d)
    assert _KEY not in dumped and "Sky appears" not in dumped and "Sky matches" not in dumped


def test_http_error_records_status_and_code(monkeypatch):
    from urllib.error import HTTPError
    body = json.dumps({"error": {"message": "Unauthorized", "type": "authentication_error",
                                 "code": "invalid_api_key"}}).encode()
    err = HTTPError("https://x", 401, "err", {}, io.BytesIO(body))
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: (_ for _ in ()).throw(err))
    p = _provider()
    with pytest.raises(ProviderError, match="authentication failed"):
        p.generate("hello")
    assert p.last_diagnostics == {"http_status": 401, "error_type": "authentication_error",
                                  "error_code": "invalid_api_key"}


def test_request_carries_minimal_effort_and_raised_cap(monkeypatch):
    assert (MAX_OUTPUT_TOKENS, REASONING_EFFORT) == (1024, "minimal")
    seen = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode())
        seen.append((body.get("reasoning_effort"), body.get("max_tokens")))
        content = json.dumps({"verdict": "supported", "rationale": "r", "cited": [0]})
        return _resp(_choice({"role": "assistant", "content": content}))

    monkeypatch.setattr(live, "urlopen", fake_urlopen)
    p = _provider()
    p.generate("hello")
    p.assess_claim("c?", ["e"])
    assert seen == [("minimal", 1024), ("minimal", 1024)]


def test_worst_case_single_call_cost_ceiling():
    p = _provider()
    p.usage_total = {"input_tokens": 1500, "output_tokens": 1024}
    assert p.estimated_cost_usd() == pytest.approx(0.006227)

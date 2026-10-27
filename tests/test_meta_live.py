"""Live Meta provider with stubbed transport. Makes NO network calls."""
import io
import json

import pytest

import providers.meta_live as live
from providers.meta_live import ConfigError, MetaConfig, MetaLiveProvider, ProviderError


def _resp(payload: dict):
    body = json.dumps(payload).encode()
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return FakeResp(body)


def _ok_payload():
    return {"choices": [{"message": {"content": json.dumps(
        {"verdict": "supported", "rationale": "cited span matches"})} }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def test_config_from_env_and_missing_key():
    cfg = MetaConfig.from_env({"MODEL_API_KEY": "  k1 ", "META_MODEL": "muse-spark-1.1"})
    assert cfg.base_url == "https://api.meta.ai/v1" and cfg.model == "muse-spark-1.1"
    assert "k1" not in repr(cfg)  # key never repr'd
    with pytest.raises(ConfigError):
        MetaConfig.from_env({})


def test_generate_parses_and_tracks_usage(monkeypatch):
    seen = {}
    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        body = json.loads(req.data.decode())
        assert body["model"] == "muse-spark-1.3" and body["temperature"] == 0
        assert body["response_format"]["type"] == "json_schema"
        assert "k-live" not in json.dumps(body)  # key only in header
        return _resp(_ok_payload())
    monkeypatch.setattr(live, "urlopen", fake_urlopen)
    p = MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": "k-live"}))
    out = p.generate("Claim: x. Evidence: x.")
    assert out == {"verdict": "supported", "rationale": "cited span matches",
                   "model": "muse-spark-1.3"}
    assert seen["url"] == "https://api.meta.ai/v1/chat/completions"
    assert seen["auth"] == "Bearer k-live"
    assert p.usage_total == {"input_tokens": 100, "output_tokens": 20}
    assert p.estimated_cost_usd() == pytest.approx(100 / 1e6 * 1.25 + 20 / 1e6 * 4.25)


def test_generate_empty_prompt_makes_no_call(monkeypatch):
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    p = MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": "k"}))
    assert p.generate("  ")["verdict"] == "unsupported"
    assert p.calls == []


def test_generate_errors_never_leak_key(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("slow")
    monkeypatch.setattr(live, "urlopen", boom)
    p = MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": "k-secret"}))
    with pytest.raises(ProviderError) as ei:
        p.generate("hello")
    assert "k-secret" not in str(ei.value)
    bad = dict(_ok_payload(), choices=[{"message": {"content": "not json"}}])
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(bad))
    with pytest.raises(ProviderError):
        p.generate("hello")

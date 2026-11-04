"""Grounded live assessment, budgets, dotenv, selection. All transport stubbed."""
import io
import json

import pytest

import providers.meta_live as live
from providers import get_provider
from providers.meta_live import (
    MAX_PROMPT_CHARS,
    MetaConfig,
    MetaLiveProvider,
    ProviderError,
    load_dotenv,
)
from providers.meta_mock import MockMetaProvider


def _resp(payload: dict):
    body = json.dumps(payload).encode()
    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return FakeResp(body)


def _grounded_payload(cited=(0,), verdict="supported"):
    return {"choices": [{"message": {"content": json.dumps(
        {"verdict": verdict, "rationale": "span matches", "cited": list(cited)})} }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10}}


def _provider(**kwargs):
    return MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": "k"}), **kwargs)


def test_build_grounded_prompt_numbers_and_caps():
    prompt = MetaLiveProvider.build_grounded_prompt("Claim C?", ["first bit", "", "second bit"])
    assert "[0] first bit" in prompt and "[1] second bit" in prompt
    assert "Claim C?" in prompt and "[index]" in prompt
    long_prompt = MetaLiveProvider.build_grounded_prompt("x" * 9000, ["y" * 9000])
    assert len(long_prompt) <= MAX_PROMPT_CHARS


def test_validate_citations_strict():
    assert MetaLiveProvider.validate_citations([0, 2, 0], 3) == (0, 2)
    assert MetaLiveProvider.validate_citations([], 1) == ()
    for bad in ([3], [-1], ["0"], [True], "0", None, {"cited": [0]}):
        with pytest.raises(ProviderError):
            MetaLiveProvider.validate_citations(bad, 3)


def test_assess_claim_success_path(monkeypatch):
    seen = {}
    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data.decode())
        seen["schema"] = body["response_format"]["json_schema"]["name"]
        assert body["temperature"] == 0 and body["max_tokens"] == live.MAX_OUTPUT_TOKENS
        return _resp(_grounded_payload())
    monkeypatch.setattr(live, "urlopen", fake_urlopen)
    out = _provider().assess_claim("The sky is blue.", ["Sky appears blue at noon."])
    assert out["verdict"] == "supported" and out["cited"] == (0,)
    assert out["usage"] == {"input_tokens": 50, "output_tokens": 10}
    assert seen["schema"] == "grounded_assessment"


def test_assess_claim_bad_citation_raises_without_recording(monkeypatch):
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(_grounded_payload(cited=(7,))))
    p = _provider()
    with pytest.raises(ProviderError, match="out-of-range"):
        p.assess_claim("Claim?", ["only one"])
    assert p.calls == [] and p.usage_total == {"input_tokens": 0, "output_tokens": 0}


def test_assess_claim_rejects_empty_input_without_http(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not call HTTP")
    monkeypatch.setattr(live, "urlopen", boom)
    p = _provider()
    with pytest.raises(ProviderError):
        p.assess_claim("  ", ["e"])
    with pytest.raises(ProviderError):
        p.assess_claim("c", [])


def test_call_budget_enforced_before_second_call(monkeypatch):
    hits = []
    def fake_urlopen(req, timeout=None):
        hits.append(1)
        return _resp(_grounded_payload())
    monkeypatch.setattr(live, "urlopen", fake_urlopen)
    p = _provider(call_budget=1)
    assert p.assess_claim("c1", ["e"])["verdict"] == "supported"
    with pytest.raises(ProviderError, match="budget exhausted"):
        p.assess_claim("c2", ["e"])
    assert len(hits) == 1


def test_load_dotenv_parsing_and_missing(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\n\nMODEL_API_KEY=abc123\nQUOTED=\"x y\"\nEMPTY=\nBAD LINE\n", encoding="utf-8")
    assert load_dotenv(str(f)) == {"MODEL_API_KEY": "abc123", "QUOTED": "x y"}
    assert load_dotenv(str(tmp_path / "nope")) == {}


def test_config_local_prefers_environment(tmp_path):
    (tmp_path / ".env").write_text("MODEL_API_KEY=file-key\nMETA_MODEL=file-model\n", encoding="utf-8")
    cfg = MetaConfig.local(str(tmp_path), env={"MODEL_API_KEY": "env-key"})
    assert cfg.api_key == "env-key" and cfg.model == "file-model"
    assert MetaConfig.local(str(tmp_path), env={}).api_key == "file-key"
    assert MetaConfig.has_key({"META_API_KEY": "z"}) is True
    assert MetaConfig.has_key({}) is False


def test_get_provider_selection(tmp_path, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    assert isinstance(get_provider("mock"), MockMetaProvider)
    (tmp_path / ".env").write_text("MODEL_API_KEY=k\n", encoding="utf-8")
    p = get_provider("live", project_dir=str(tmp_path), model="muse-wonder-1.0", call_budget=2)
    assert isinstance(p, MetaLiveProvider) and p.model == "muse-wonder-1.0" and p.call_budget == 2
    with pytest.raises(ValueError):
        get_provider("turbo")
    with pytest.raises(Exception, match="[Kk]ey"):
        get_provider("live", project_dir=str(tmp_path / "empty"))

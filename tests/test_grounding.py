"""Evidence selection for grounded calls: ranking, caps, citation mapping.

All transport stubbed; the model must only ever cite evidence it received.
"""
import io
import json

import providers.meta_live as live
from providers.meta_live import (
    MAX_EVIDENCE_ITEMS,
    MAX_PROMPT_CHARS,
    MetaConfig,
    MetaLiveProvider,
    ProviderError,
)
from pruvcore.pipeline import rank_by_overlap

import pytest


def _provider(**kwargs):
    return MetaLiveProvider(MetaConfig.from_env({"MODEL_API_KEY": "k"}), **kwargs)


def _resp(payload: dict):
    body = json.dumps(payload).encode()

    class FakeResp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return FakeResp(body)


def _grounded_payload(cited, verdict="supported"):
    return {"choices": [{"message": {"content": json.dumps(
        {"verdict": verdict, "rationale": "span matches", "cited": list(cited)})}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10}}


def _forty(relevant_at=30):
    items = [f"filler padding line {n} about weather and transit" for n in range(40)]
    items[relevant_at] = "Alpha beta decisive span here"
    return items


def test_rank_by_overlap_orders_with_stable_ties():
    assert rank_by_overlap("Alpha beta", ["zzz qq", "Alpha beta span", "beta alpha too"]) == [1, 2, 0]
    assert rank_by_overlap("", ["b", "a"]) == [0, 1]
    assert rank_by_overlap("Alpha beta", ["zzz", "qqq"]) == [0, 1]
    first = rank_by_overlap("order damaged", _forty())
    assert rank_by_overlap("order damaged", _forty()) == first  # deterministic


def test_selection_sends_relevant_first_with_original_map():
    sel = MetaLiveProvider.select_grounding_evidence("Alpha beta.", _forty())
    assert sel["sent"][0] == 30
    assert "[0] Alpha beta decisive span here" in sel["prompt"]
    assert len(sel["sent"]) == MAX_EVIDENCE_ITEMS
    assert len(sel["prompt"]) <= MAX_PROMPT_CHARS
    assert set(sel["sent"]) | set(sel["omitted"]) == set(range(40))
    assert sel["omitted"] == tuple(sorted(sel["omitted"]))
    assert sel["shortened"] == 0


def test_selection_fits_whole_items_within_char_budget():
    items = ["Sentence one here. " * 60] * 40  # ~1140 chars each
    sel = MetaLiveProvider.select_grounding_evidence("Sentence one", items)
    assert len(sel["sent"]) <= MAX_EVIDENCE_ITEMS
    assert len(sel["prompt"]) <= MAX_PROMPT_CHARS
    assert sel["shortened"] == len(sel["sent"]) and sel["omitted"]
    assert " […]" in sel["prompt"]
    tight = MetaLiveProvider.select_grounding_evidence("Sentence one", items, max_chars=1200)
    assert 0 < len(tight["sent"]) < len(sel["sent"])
    assert len(tight["prompt"]) <= 1200
    assert tight["sent"] == sel["sent"][: len(tight["sent"])]  # top-ranked stay contiguous


def test_shortening_keeps_sentence_boundary_and_marks():
    short, was = MetaLiveProvider._shorten_item("First sentence here. " + "x" * 900)
    assert (short, was) == ("First sentence here. […]", True)
    kept, was = MetaLiveProvider._shorten_item("short line")
    assert (kept, was) == ("short line", False)
    hard, was = MetaLiveProvider._shorten_item("z" * 900)
    assert was is True and len(hard) == 800 and hard.endswith(" […]")


def test_assess_claim_maps_citations_to_original_indexes(monkeypatch):
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(_grounded_payload([0, 2])))
    out = _provider().assess_claim("Alpha beta", ["zzz qq", "Alpha beta span", "mmm nn"])
    assert out["sent"] == (1, 0, 2)  # ranked: relevant item numbered [0]
    assert out["cited"] == (1, 2)  # positions mapped back to original indexes
    assert out["omitted"] == () and out["shortened"] == 0


def test_assess_claim_rejects_index_beyond_sent_range(monkeypatch):
    # Cited [15] exists in the 40-item collection but was never sent: the old
    # full-length bound accepted it; the sent-range bound must reject it.
    monkeypatch.setattr(live, "urlopen", lambda *a, **k: _resp(_grounded_payload([15])))
    provider = _provider()
    with pytest.raises(ProviderError, match="out-of-range"):
        provider.assess_claim("Alpha beta.", _forty())
    assert provider.calls == []


def test_assess_claim_all_empty_raises_without_http(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not call HTTP")

    monkeypatch.setattr(live, "urlopen", boom)
    with pytest.raises(ProviderError, match="non-empty"):
        _provider().assess_claim("claim?", ["", "   "])


def test_selection_deterministic():
    first = MetaLiveProvider.select_grounding_evidence("Alpha beta.", _forty())
    assert MetaLiveProvider.select_grounding_evidence("Alpha beta.", _forty()) == first

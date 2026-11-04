"""Saved-workspace restore: validation, legacy files, corruption handling."""
import json

import pytest

from pruvcards.render import assessment_to_card
from pruvcore.pipeline import assess
from pruvcore.schemas import Claim, EvidenceRef
from pruvcore.store import export_report, list_runs, load_run, restore_workspace, save_run


def _card(status="supported"):
    (result,) = assess([Claim(id="k1", text="Alpha beta")],
                       [EvidenceRef(id="e1", text="Alpha beta gamma", source="s", locator="L")])
    card = assessment_to_card(result, {"e1": EvidenceRef(id="e1", text="Alpha beta gamma",
                                                         source="s", locator="L")})
    assert card["status"] == status
    return card


def _saved(tmp_path, **overrides):
    payload = {"saved_at": "2026-01-01T00:00:00+00:00", "name": "w1", "mode": "custom",
               "engine": "mock", "provider": "mock", "model": "",
               "inputs": {"objective": "o", "claims": "Alpha beta", "evidence": "Alpha beta"},
               "cards": [_card()], "summary": {"supported": 1, "total": 1}}
    payload.update(overrides)
    path = save_run(str(tmp_path), payload.pop("name"), payload.pop("mode"), payload.pop("inputs"),
                    payload.pop("cards"), payload.pop("summary"), engine=payload.get("engine", "mock"),
                    provider=payload.get("provider", "mock"), model=payload.get("model", ""))
    return path


def test_restore_round_trip_preserves_provenance(tmp_path):
    _saved(tmp_path, engine="live", provider="meta-live", model="muse-spark-1.3")
    data = load_run(str(tmp_path), list_runs(str(tmp_path))[0]["file"])
    out = restore_workspace(data)
    assert out["legacy"] is False and out["engine"] == "live"
    assert out["provider"] == "meta-live" and out["model"] == "muse-spark-1.3"
    assert out["inputs"]["claims"] == "Alpha beta"
    (assessment,) = out["assessments"]
    assert assessment.verdict.value == "supported" and assessment.evidence_ids == ("e1",)
    assert out["evidence"][0].locator == "L"
    assert "Engine: live" in export_report(data) and "muse-spark-1.3" in export_report(data)


def test_restore_legacy_inputs_only(tmp_path):
    runs_dir = tmp_path / ".pruvchat_runs"
    runs_dir.mkdir()
    (runs_dir / "old.json").write_text(json.dumps({"name": "old", "mode": "custom",
                                                   "inputs": {"claims": "c"}}), encoding="utf-8")
    data = load_run(str(tmp_path), "old.json")
    out = restore_workspace(data)
    assert out["legacy"] is True and out["assessments"] == [] and out["evidence"] == []
    assert out["inputs"] == {"claims": "c"} and out["engine"] == "mock"


def test_restore_rejects_corruption_without_invention(tmp_path):
    base = {"saved_at": "t", "name": "w", "mode": "custom", "inputs": {"claims": "c"},
            "cards": [_card()], "summary": {}}
    assert restore_workspace(dict(base))["legacy"] is False
    bad_inputs = dict(base, inputs={"claims": 42})
    with pytest.raises(ValueError, match="inputs"):
        restore_workspace(bad_inputs)
    for mutate, _label in [
        ({"status": "maybe"}, "status"),
        ({"claim": None}, "claim"),
        ({"score": "high"}, "score"),
        ({"evidence_ids": "e1"}, "evidence_ids"),
        ({"citations": [{"id": 7}]}, "citation"),
        ({"uncertainty": "unknown"}, "uncertainty"),
    ]:
        card = dict(_card())
        card.update(mutate)
        with pytest.raises(ValueError):
            restore_workspace(dict(base, cards=[card]))
    with pytest.raises(ValueError, match="inputs"):
        restore_workspace({"cards": []})
    with pytest.raises(ValueError, match="inputs"):
        restore_workspace("nope")


def test_export_report_labels_live_mock_and_fallback(tmp_path):
    mock_card = dict(_card())
    live_card = dict(_card(), method="live Meta API (m1) — no overlap score", score=1.0)
    fb_card = dict(_card(), method="live fallback: unverified (x)",
                   rationale="UNVERIFIED — nothing.", status="unsupported")
    report = export_report({"name": "w", "mode": "custom", "saved_at": "t",
                            "engine": "live", "provider": "meta-live", "model": "m1",
                            "summary": {"supported": 2, "contested": 0, "unsupported": 1,
                                        "total": 3},
                            "cards": [mock_card, live_card, fb_card]})
    assert "- Engine: live  |  Provider: meta-live (m1)" in report
    assert "(heuristic overlap" in report
    assert "(live Meta API verdict, no overlap score)" in report
    assert "live fallback, UNVERIFIED, not a verdict" in report


def test_restore_unresolvable_reference_renders_unresolved(tmp_path):
    from pruvcards.render import assessment_to_card

    card = dict(_card())
    card["evidence_ids"] = ["ghost"]
    card["citations"] = []
    out = restore_workspace({"mode": "custom", "inputs": {"claims": "c"}, "cards": [card]})
    (assessment,) = out["assessments"]
    assert assessment.evidence_ids == ("ghost",)
    rendered = assessment_to_card(assessment, {e.id: e for e in out["evidence"]})
    assert rendered["citations"][0]["source"] == "unresolved"
    assert "Not verified" in rendered["citations"][0]["excerpt"]


def test_load_rejects_unparseable_and_bad_inputs(tmp_path):
    runs_dir = tmp_path / ".pruvchat_runs"
    runs_dir.mkdir()
    (runs_dir / "broken.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError):
        load_run(str(tmp_path), "broken.json")
    (runs_dir / "nocards.json").write_text(json.dumps({"inputs": {}}), encoding="utf-8")
    assert load_run(str(tmp_path), "nocards.json")["cards"] == []

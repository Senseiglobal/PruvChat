"""Visa Document Readiness Review: coverage labels, fixture, safety copy."""
import json
import os

from pruvcore.pipeline import assess
from pruvcore.schemas import Claim, EvidenceRef, Verdict
from pruvcore.visa import (COVERAGE_HELP, MISSING, NEEDS_ATTENTION, READY,
                           SAFETY_NOTE, coverage_for, coverage_line,
                           coverage_summary)

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _load_visa():
    with open(os.path.join(_FIX, "visa_checklist.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _pooled_run(data):
    """Mirror the app: every item scored against one shared evidence pool."""
    claims = [Claim(id=f"v{i + 1}", text=item["requirement"])
              for i, item in enumerate(data["items"])]
    evidence = [EvidenceRef(id=e["id"], text=e["text"])
                for item in data["items"] for e in item["evidence"]]
    return assess(claims, evidence), evidence


def test_coverage_labels_map_one_to_one_from_verdicts():
    assert (READY, NEEDS_ATTENTION, MISSING) == ("Ready for review", "Needs attention",
                                                 "Missing evidence")
    assert coverage_for(Verdict.SUPPORTED) == READY
    assert coverage_for(Verdict.CONTESTED) == NEEDS_ATTENTION
    assert coverage_for(Verdict.UNSUPPORTED) == MISSING
    assert coverage_for("supported") == READY
    assert coverage_for("nope") == MISSING  # unknown stays Missing, fail closed


def test_coverage_summary_counts_and_line():
    results, _ = _pooled_run(_load_visa())
    summary = coverage_summary(results)
    assert summary == {"ready": 1, "needs_attention": 1, "missing": 1, "total": 3}
    line = coverage_line(summary)
    assert "1 Ready for review" in line and "1 Needs attention" in line
    assert "1 Missing evidence" in line
    assert line.endswith("(3 total)")


def test_visa_fixture_is_synthetic_and_deterministic():
    data = _load_visa()
    assert "SYNTHETIC" in data["label"] and data["mode"] == "visa"
    assert data["source_name"] and data["source_date"]
    first, _ = _pooled_run(data)
    assert [r.verdict for r in first] == [Verdict.SUPPORTED, Verdict.CONTESTED,
                                          Verdict.UNSUPPORTED]
    second, _ = _pooled_run(data)
    assert [r.verdict for r in second] == [r.verdict for r in first]


def test_safety_copy_states_limits_plainly():
    assert "not approval" in SAFETY_NOTE
    assert "immigration professional" in SAFETY_NOTE
    assert "official" in SAFETY_NOTE
    assert "present for review" in COVERAGE_HELP
    assert "will be approved" in COVERAGE_HELP
    for text in (SAFETY_NOTE, COVERAGE_HELP):
        assert "\u2014" not in text and "\u2013" not in text and " -- " not in text


def test_visa_save_round_trip_keeps_source_and_inputs(tmp_path):
    from pruvcards.render import assessment_to_card
    from pruvcore.store import list_runs, load_run, restore_workspace, save_run

    data = _load_visa()
    results, evidence = _pooled_run(data)
    by_id = {e.id: e for e in evidence}
    cards = [assessment_to_card(r, by_id) for r in results]
    inputs = {"requirements": "\n".join(i["requirement"] for i in data["items"]),
              "source_name": data["source_name"], "source_date": data["source_date"],
              "evidence": "\n".join(e.text for e in evidence)}
    save_run(str(tmp_path), "visa check", "visa", inputs, cards,
             {"supported": 1, "contested": 1, "unsupported": 1, "total": 3})
    assert len(list_runs(str(tmp_path))) == 1
    restored = restore_workspace(load_run(str(tmp_path), list_runs(str(tmp_path))[0]["file"]))
    assert restored["mode"] == "visa" and not restored["legacy"]
    assert restored["inputs"]["source_name"] == data["source_name"]
    assert len(restored["assessments"]) == 3
    assert [coverage_for(a.verdict) for a in restored["assessments"]] == [
        READY, NEEDS_ATTENTION, MISSING]


def test_global_talent_demo_fixture_verdicts():
    with open(os.path.join(_FIX, "visa_global_talent.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert "SYNTHETIC" in data["label"] and "No real applicant data" in data["label"]
    results, _ = _pooled_run(data)
    assert [r.verdict for r in results] == [Verdict.SUPPORTED, Verdict.CONTESTED,
                                            Verdict.UNSUPPORTED]
    assert coverage_summary(results) == {"ready": 1, "needs_attention": 1,
                                         "missing": 1, "total": 3}


def test_country_list_covers_destinations():
    from pruvcore.countries import COUNTRIES, QUICK_COUNTRIES

    assert len(COUNTRIES) >= 185 and len(set(COUNTRIES)) == len(COUNTRIES)
    for name in ("United Kingdom", "United States", "Canada", "Australia",
                 "Germany", "France", "Japan"):
        assert name in COUNTRIES
    assert "Other country" not in COUNTRIES
    for _, full in QUICK_COUNTRIES:
        if full != "Other country":
            assert full in COUNTRIES

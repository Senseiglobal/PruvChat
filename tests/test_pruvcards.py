"""Complete PruvCard rendering: blockquotes, citations, all three modes."""
import importlib
import json
import os
import re

from pruvcards.render import (
    assessment_to_card,
    assessments_to_markdown,
    summarize,
    to_blockquote,
)
from pruvcore.pipeline import annotate_contradictions, assess, extract_claims
from pruvcore.schemas import Claim, EvidenceRef

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
_REQUIRED_CARD_KEYS = ("title", "claim", "claim_id", "status", "score", "method", "rationale",
                       "evidence_ids", "citations", "contradicted_by", "uncertainty", "next_action")


def _load(name):
    with open(os.path.join(_FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_blockquote_single_multiline_and_empty():
    assert to_blockquote("hello") == "> hello"
    assert to_blockquote("a\n\nb") == "> a\n>\n> b"
    assert to_blockquote("  ") == "> (no excerpt)"
    assert to_blockquote("") == "> (no excerpt)"
    assert to_blockquote("# not-a-heading *x*") == "> # not-a-heading *x*"


def test_card_has_complete_structure_with_citations():
    ev = [EvidenceRef(id="e1", text="Alpha beta gamma delta", source="upload",
                      locator="upload:notes.txt")]
    (result,) = annotate_contradictions(
        assess([Claim(id="c1", text="Alpha beta gamma")], ev), ev)
    card = assessment_to_card(result, {e.id: e for e in ev})
    for key in _REQUIRED_CARD_KEYS:
        assert key in card, key
    assert card["citations"] == [{"id": "e1", "source": "upload",
                                  "locator": "upload:notes.txt", "excerpt": ev[0].text}]
    assert to_blockquote(card["citations"][0]["excerpt"]).startswith(">")


def test_unknown_and_empty_evidence_render_safely():
    (result,) = assess([Claim(id="c1", text="Alpha beta")],
                       [EvidenceRef(id="e1", text="Alpha beta")])
    card = assessment_to_card(result, {})
    # H2: unresolvable references must say so explicitly, never render blank.
    assert card["citations"] == [{"id": "e1", "source": "unresolved", "locator": "",
                                  "excerpt": "(unresolved reference: no matching source. Not verified.)"}]
    assert "Not verified" in to_blockquote(card["citations"][0]["excerpt"])
    lonely = assess([Claim(id="c9", text="Zebra quasar")], [])
    md = assessments_to_markdown(lonely)
    assert "Evidence refs: none" in md and "UNSUPPORTED" in md


def test_multiple_findings_markdown_and_summary():
    claims = extract_claims("Alpha beta gamma. Zebra quasar fjord. Alpha one two three.")
    ev = [EvidenceRef(id="e1", text="Alpha beta gamma delta")]
    results = annotate_contradictions(assess(claims, ev), ev)
    md = assessments_to_markdown(results, {e.id: e for e in ev})
    assert md.count("## ") == 3
    assert "heuristic overlap" in md and "Next action" in md
    assert summarize(results) == {"supported": 1, "contested": 1, "unsupported": 1, "total": 3}


def test_requirements_mode_cards():
    data = _load("requirements_review.json")
    cards = []
    for i, item in enumerate(data["items"]):
        ev = [EvidenceRef(id=e["id"], text=e["text"], source="fixture",
                          locator=f"fixture:{data['items'][i]['requirement'][:20]}")
              for e in item["evidence"]]
        (result,) = annotate_contradictions(
            assess([Claim(id=f"r{i + 1}", text=item["requirement"])], ev), ev)
        cards.append(assessment_to_card(result, {e.id: e for e in ev}))
    assert [c["status"] for c in cards] == ["supported", "contested", "unsupported"]
    assert all(c["citations"] and c["citations"][0]["locator"].startswith("fixture:")
               for c in cards[:2])
    assert cards[2]["citations"] == []


def test_disputes_mode_both_sides_cards():
    data = _load("business_dispute.json")
    claim = Claim(id="d1", text=data["claim"])
    outs = {}
    for side in ("side_a", "side_b"):
        ev = [EvidenceRef(id=e["id"], text=e["text"], source=data[side]["name"]) for e in data[side]["evidence"]]
        (result,) = assess([claim], ev)
        outs[side] = assessment_to_card(result, {e.id: e for e in ev})
    assert outs["side_a"]["status"] == "supported"
    assert outs["side_b"]["status"] == "contested"
    assert outs["side_a"]["citations"][0]["source"] == "Buyer"
    assert outs["side_b"]["citations"][0]["source"] == "Seller"


def test_app_import_surface_matches_render_module():
    """Every name app.py imports from pruvcards.render must exist there.

    Guards the ImportError class where the app asks for a helper the module
    does not define (as opposed to stale-process caching, which a restart fixes).
    """
    app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    with open(app_path, encoding="utf-8") as fh:
        src = fh.read()
    match = re.search(r"from pruvcards\.render import ([A-Za-z0-9_, ]+)", src)
    assert match, "app.py must import render helpers from pruvcards.render"
    wanted = [n.strip() for n in match.group(1).split(",") if n.strip()]
    assert "to_blockquote" in wanted
    module = importlib.import_module("pruvcards.render")
    for name in wanted:
        assert callable(getattr(module, name, None)), name
    package = importlib.import_module("pruvcards")
    for name in wanted:
        assert name in package.__all__, name


def test_markdown_distinguishes_live_mock_and_fallback():
    from pruvcore.pipeline import fallback_unverified
    from pruvcore.schemas import Assessment, Verdict

    (mocked,) = assess([Claim(id="c1", text="Alpha beta")],
                       [EvidenceRef(id="e1", text="Alpha beta gamma")])
    live = Assessment(claim=Claim(id="c2", text="Alpha beta"), verdict=Verdict.SUPPORTED,
                      score=1.0, rationale="span matches", evidence_ids=("e1",),
                      uncertainty="low", method="live Meta API (m1) — no overlap score")
    (fb,) = fallback_unverified([Claim(id="c3", text="Alpha beta")], "no evidence.")
    by_id = {"e1": EvidenceRef(id="e1", text="Alpha beta gamma", source="pasted",
                               locator="pasted text #1")}
    md = assessments_to_markdown([mocked, live, fb], by_id,
                                 header="# PruvChat findings — Custom\nEngine: x")
    assert md.startswith("# PruvChat findings — Custom\nEngine: x")
    assert "(heuristic overlap 1.0)" in md
    assert "(live Meta API verdict, no overlap score)" in md
    assert "live fallback, UNVERIFIED, not a verdict" in md
    assert "Next action:" in md and "pasted text #1" in md and "Alpha beta gamma" in md


def test_plain_verdict_covers_all_statuses():
    from pruvcards.render import plain_verdict

    assert plain_verdict("supported") == "The evidence backs this claim."
    assert "human" in plain_verdict("contested")
    assert plain_verdict("unsupported") == "No supporting evidence was found for this claim."
    assert plain_verdict("bogus") == "This finding needs human review."


def test_custom_mode_cards():
    data = _load("custom_assessment.json")
    claims = [Claim(id=f"k{i + 1}", text=t) for i, t in enumerate(data["claims"])]
    ev = [EvidenceRef(id=e["id"], text=e["text"], source="custom") for e in data["evidence"]]
    results = annotate_contradictions(assess(claims, ev), ev)
    cards = [assessment_to_card(r, {e.id: e for e in ev}) for r in results]
    assert [c["status"] for c in cards] == ["supported", "unsupported"]
    assert cards[1]["citations"] == [] and cards[1]["uncertainty"] == "High"

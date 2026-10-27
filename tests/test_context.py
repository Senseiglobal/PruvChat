"""Contradictions, exact citations, uncertainty, honest method labels."""
from pruvcards.render import assessment_to_card, assessments_to_markdown
from pruvcore.pipeline import annotate_contradictions, assess, find_contradictions, uncertainty_for
from pruvcore.schemas import Claim, EvidenceRef, Verdict


def _ev():
    return [
        EvidenceRef(id="a1", text="Order 1042 arrived with all parts included",
                    source="seller", locator="upload:packing-slip.txt"),
        EvidenceRef(id="b1", text="Order 1042 arrived damaged and missing parts",
                    source="buyer", locator="upload:complaint.txt"),
        EvidenceRef(id="c1", text="Warehouse weather was sunny all week", source="log"),
    ]


def test_find_contradictions_flags_negated_pair_only():
    pairs = find_contradictions(_ev())
    assert len(pairs) == 1
    a, b, shared = pairs[0]
    assert {a, b} == {"a1", "b1"}
    assert "order" in shared and "1042" in shared


def test_annotate_marks_claim_with_tension():
    claim = Claim(id="d1", text="Item reported damaged, several components missing")
    ev = _ev()
    (result,) = annotate_contradictions(assess([claim], ev), ev)
    assert result.verdict is Verdict.CONTESTED
    assert result.evidence_ids == ("b1",)
    assert result.contradicted_by == ("a1",)
    assert result.uncertainty == "medium"


def test_annotate_flags_conflict_inside_matched_set():
    claim = Claim(id="d1", text="Order 1042 arrived damaged and missing parts")
    ev = _ev()
    (result,) = annotate_contradictions(assess([claim], ev), ev)
    assert result.verdict is Verdict.SUPPORTED
    assert sorted(result.contradicted_by) == ["a1", "b1"]
    assert result.uncertainty == "medium"


def test_uncertainty_mapping():
    assert uncertainty_for(Verdict.SUPPORTED, False) == "low"
    assert uncertainty_for(Verdict.SUPPORTED, True) == "medium"
    assert uncertainty_for(Verdict.CONTESTED, False) == "medium"
    assert uncertainty_for(Verdict.UNSUPPORTED, False) == "high"


def test_card_carries_exact_citations_and_method():
    claim = Claim(id="d1", text="Item reported damaged, several components missing")
    ev = _ev()
    (result,) = annotate_contradictions(assess([claim], ev), ev)
    card = assessment_to_card(result, {e.id: e for e in ev})
    assert "not an AI judgment" in card["method"]
    assert card["contradicted_by"] == ["a1"]
    assert card["citations"][0]["locator"] == "upload:complaint.txt"
    assert "missing parts" in card["citations"][0]["excerpt"]
    md = assessments_to_markdown([result], {e.id: e for e in ev})
    assert "heuristic overlap" in md and "Contradiction flags" in md
    assert "upload:complaint.txt" in md

"""Core assessment workflow: claims, scoring, verdicts, citation integrity."""
from pruvcore.pipeline import assess, extract_claims, fallback_unverified, score_claim
from pruvcore.schemas import Claim, EvidenceRef, Verdict


def test_extract_claims_splits_sentences():
    claims = extract_claims("First claim here. Second claim here!")
    assert [c.text for c in claims] == ["First claim here.", "Second claim here!"]
    assert [c.id for c in claims] == ["c1", "c2"]


def test_extract_claims_empty_input():
    assert extract_claims("") == []
    assert extract_claims("   ") == []


def test_score_claim_full_overlap():
    claim = Claim(id="c1", text="Order arrived damaged yesterday")
    ev = [EvidenceRef(id="e1", text="Order arrived damaged yesterday")]
    score, matched = score_claim(claim, ev)
    assert score == 1.0
    assert matched == ("e1",)


def test_score_claim_no_overlap_and_no_evidence():
    claim = Claim(id="c1", text="Order arrived damaged yesterday")
    assert score_claim(claim, []) == (0.0, ())
    ev = [EvidenceRef(id="e9", text="Weather is sunny in Lisbon")]
    assert score_claim(claim, ev) == (0.0, ())


def test_assess_verdict_mapping():
    claims = [
        Claim(id="c1", text="alpha beta gamma delta"),
        Claim(id="c2", text="alpha one two three"),
        Claim(id="c3", text="zebra quasar fjord"),
    ]
    ev = [EvidenceRef(id="e1", text="alpha beta gamma delta")]
    results = assess(claims, ev)
    assert [r.verdict for r in results] == [
        Verdict.SUPPORTED,  # 4/4 overlap
        Verdict.CONTESTED,  # 1/4 overlap
        Verdict.UNSUPPORTED,  # 0 overlap
    ]


def test_assess_is_deterministic():
    claims = extract_claims("Order arrived damaged. Refund was issued.")
    ev = [EvidenceRef(id="e1", text="Order arrived damaged in transit.")]
    assert assess(claims, ev) == assess(claims, ev)


def test_citation_integrity_ids_reference_supplied_evidence_only():
    claims = [Claim(id="c1", text="alpha beta"), Claim(id="c2", text="nothing shared")]
    ev = [EvidenceRef(id="e1", text="alpha beta gamma")]
    results = assess(claims, ev)
    for r in results:
        assert set(r.evidence_ids) <= {"e1"}
    assert results[1].verdict is Verdict.UNSUPPORTED
    assert results[1].evidence_ids == ()


def test_contradictory_evidence_flips_verdict():
    claim = Claim(id="c1", text="Order 1042 arrived damaged and missing parts")
    buyer = [EvidenceRef(id="a1", text="Order 1042 arrived with a cracked panel and missing screws")]
    seller = [EvidenceRef(id="b1", text="Order 1042 passed warehouse inspection before shipping")]
    assert assess([claim], buyer)[0].verdict is Verdict.SUPPORTED
    assert assess([claim], seller)[0].verdict is Verdict.CONTESTED


def test_fallback_unverified_shape_and_wording():
    (only,) = fallback_unverified([Claim(id="c1", text="Alpha beta")], "no evidence supplied.")
    assert only.verdict is Verdict.UNSUPPORTED and only.score == 0.0
    assert only.evidence_ids == () and only.uncertainty == "high"
    assert only.rationale.startswith("UNVERIFIED") and "no evidence supplied" in only.rationale
    assert "live fallback: unverified" in only.method
    assert fallback_unverified([], "reason") == []
    again = fallback_unverified([Claim(id="c1", text="Alpha beta")], "no evidence supplied.")
    assert again == [only]  # deterministic


def test_fallback_unverified_never_runs_keyword_scoring():
    # The mock pipeline would call this SUPPORTED; the fallback must not,
    # and must carry the caller-supplied provenance method.
    (mocked,) = assess([Claim(id="c1", text="Alpha beta")],
                       [EvidenceRef(id="e1", text="Alpha beta gamma")])
    assert mocked.verdict is Verdict.SUPPORTED
    (fb,) = fallback_unverified([Claim(id="c1", text="Alpha beta")], "no live call made.",
                                method="live fallback: unverified (inputs incomplete)")
    assert fb.verdict is Verdict.UNSUPPORTED and fb.score == 0.0
    assert fb.method == "live fallback: unverified (inputs incomplete)"

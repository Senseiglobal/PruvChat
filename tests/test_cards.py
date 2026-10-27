"""PruvCards rendering: card shape, Markdown report, summary counts."""
from pruvcards.render import assessment_to_card, assessments_to_markdown, summarize
from pruvcore.pipeline import assess, extract_claims
from pruvcore.schemas import EvidenceRef


def _sample():
    claims = extract_claims("Alpha beta gamma. Zebra quasar fjord.")
    ev = [EvidenceRef(id="e1", text="Alpha beta gamma delta")]
    return assess(claims, ev)


def test_card_has_required_fields():
    card = assessment_to_card(_sample()[0])
    for key in ("title", "claim", "status", "score", "rationale",
                "evidence_ids", "uncertainty", "next_action"):
        assert key in card
    assert card["status"] == "supported"
    assert card["evidence_ids"] == ["e1"]


def test_markdown_and_summary():
    results = _sample()
    md = assessments_to_markdown(results)
    assert "SUPPORTED" in md and "UNSUPPORTED" in md
    assert summarize(results) == {"supported": 1, "contested": 0, "unsupported": 1, "total": 2}
    assert assessments_to_markdown([]) == "No claims assessed."

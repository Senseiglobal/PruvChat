"""PruvCards: render assessments to card dicts, Markdown, and summaries."""
from __future__ import annotations

from pruvcore.schemas import Assessment, Verdict

_NEXT_ACTION = {
    Verdict.SUPPORTED: "Keep the cited source on file; no further evidence needed.",
    Verdict.CONTESTED: "Gather one corroborating source and re-run the assessment.",
    Verdict.UNSUPPORTED: "Supply supporting evidence or revise the claim.",
}


def assessment_to_card(assessment: Assessment, evidence_by_id: dict | None = None) -> dict:
    """Convert one Assessment to a plain-dict card for UI rendering.

    Pass evidence_by_id (id -> EvidenceRef) to include exact excerpts/locators.
    """
    by_id = evidence_by_id or {}
    citations = []
    for eid in assessment.evidence_ids:
        ev = by_id.get(eid)
        if ev is None:
            citations.append({"id": eid, "source": "?", "locator": "", "excerpt": ""})
        else:
            citations.append({"id": eid, "source": ev.source, "locator": ev.locator or ev.source,
                              "excerpt": ev.text[:280]})
    return {
        "title": f"{assessment.verdict.value.upper()}: {assessment.claim.text[:60]}",
        "claim": assessment.claim.text,
        "claim_id": assessment.claim.id,
        "status": assessment.verdict.value,
        "score": assessment.score,
        "method": assessment.method,
        "rationale": assessment.rationale,
        "evidence_ids": list(assessment.evidence_ids),
        "citations": citations,
        "contradicted_by": list(assessment.contradicted_by),
        "uncertainty": (assessment.uncertainty or "medium").capitalize(),
        "next_action": _NEXT_ACTION[assessment.verdict],
    }


def assessments_to_markdown(assessments: list, evidence_by_id: dict | None = None) -> str:
    """Render assessments as a Markdown report section."""
    if not assessments:
        return "No claims assessed."
    lines = []
    for a in assessments:
        card = assessment_to_card(a, evidence_by_id)
        lines.append(f"## {card['title']}")
        lines.append(f"- Status: **{card['status']}** (heuristic overlap {card['score']})")
        lines.append(f"- Method: {card['method']}")
        lines.append(f"- Claim ({card['claim_id']}): {card['claim']}")
        lines.append(f"- Rationale: {card['rationale']}")
        if card["citations"]:
            lines.append("- Evidence:")
            for c in card["citations"]:
                ref = f"{c['id']} [{c['locator']}]" if c["locator"] else c["id"]
                lines.append(f"  - {ref}: \"{c['excerpt']}\"")
        else:
            lines.append("- Evidence refs: none")
        if card["contradicted_by"]:
            lines.append(f"- Contradiction flags (heuristic): {', '.join(card['contradicted_by'])}")
        lines.append(f"- Uncertainty: {card['uncertainty']}")
        lines.append(f"- Next action: {card['next_action']}")
        lines.append("")
    return "\n".join(lines).strip()


def summarize(assessments: list) -> dict:
    """Count assessments by verdict."""
    counts = {v.value: 0 for v in Verdict}
    for a in assessments:
        counts[a.verdict.value] += 1
    counts["total"] = len(assessments)
    return counts

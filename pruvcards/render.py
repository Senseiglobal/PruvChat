"""PruvCards: render assessments to card dicts, Markdown, and summaries."""
from __future__ import annotations

from pruvcore.schemas import Assessment, Verdict

_NEXT_ACTION = {
    Verdict.SUPPORTED: "Keep the cited source on file. No further evidence is needed.",
    Verdict.CONTESTED: "Gather one supporting source and run the assessment again.",
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
            citations.append({"id": eid, "source": "unresolved", "locator": "",
                              "excerpt": "(unresolved reference: no matching source. Not verified.)"})
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


def _verdict_basis(method: str, score) -> str:
    """One-line truthful basis for a verdict: heuristic, live, or fallback."""
    method = str(method or "")
    if method.startswith("live fallback"):
        return "live fallback, UNVERIFIED, not a verdict"
    if method.startswith("live"):
        return "live Meta API verdict, no overlap score"
    return f"heuristic overlap {score}"


def assessments_to_markdown(assessments: list, evidence_by_id: dict | None = None,
                            header: str | None = None) -> str:
    """Render assessments as a Markdown report section.

    header (mode/engine/provenance lines) is prepended verbatim when given.
    """
    if not assessments:
        return "No claims assessed."
    lines = ([header, ""] if header else [])
    for a in assessments:
        card = assessment_to_card(a, evidence_by_id)
        lines.append(f"## {card['title']}")
        lines.append(f"- Status: **{card['status']}** ({_verdict_basis(card['method'], card['score'])})")
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


_PLAIN_VERDICT = {
    "supported": "The evidence backs this claim.",
    "contested": "The evidence partly backs this claim or disagrees. Please ask a human to review it.",
    "unsupported": "No supporting evidence was found for this claim.",
}


def plain_verdict(status: str) -> str:
    """One plain-language sentence per verdict status. Pure function."""
    return _PLAIN_VERDICT.get(str(status or "").lower(), "This finding needs human review.")


def to_blockquote(text: str) -> str:
    """Render an excerpt as Markdown blockquote, preserving line breaks.

    Used by the UI so source excerpts are visually distinct from generated
    assessment text. Blank input yields an explicit placeholder.
    """
    body = (text or "").strip()
    if not body:
        return "> (no excerpt)"
    return "\n".join(f"> {line}" if line.strip() else ">" for line in body.splitlines())


def summarize(assessments: list) -> dict:
    """Count assessments by verdict."""
    counts = {v.value: 0 for v in Verdict}
    for a in assessments:
        counts[a.verdict.value] += 1
    counts["total"] = len(assessments)
    return counts

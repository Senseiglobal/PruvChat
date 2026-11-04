"""Deterministic mock assessment pipeline. No network, no secrets, no randomness."""
from __future__ import annotations

import re

from pruvcore.schemas import Assessment, Claim, EvidenceRef, Verdict

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been it its this that shall must will should".split()
)

# Negation markers for the contradiction heuristic (deterministic, explainable).
NEGATIONS = frozenset(
    "not no never without missing lacks lacking failed failure damaged broken defective "
    "denied refused unpaid late wrong incorrect false".split()
)


def _tokens(text: str) -> set:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS}


def extract_claims(text: str, prefix: str = "c") -> list:
    """Split text into sentence-level claims. Empty input -> []."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    return [Claim(id=f"{prefix}{i + 1}", text=p) for i, p in enumerate(parts)]


def score_claim(claim: Claim, evidence: list) -> tuple:
    """Keyword-overlap score in [0,1]; returns (score, matched_evidence_ids)."""
    claim_tokens = _tokens(claim.text)
    if not claim_tokens or not evidence:
        return 0.0, ()
    matched: list = []
    best = 0.0
    for ev in evidence:
        ev_tokens = _tokens(ev.text)
        if not ev_tokens:
            continue
        overlap = claim_tokens & ev_tokens
        score = len(overlap) / len(claim_tokens)
        if overlap:
            matched.append(ev.id)
        best = max(best, score)
    return round(min(1.0, best), 3), tuple(matched)


def _verdict(score: float) -> Verdict:
    if score >= 0.5:
        return Verdict.SUPPORTED
    if score >= 0.2:
        return Verdict.CONTESTED
    return Verdict.UNSUPPORTED


def rank_by_overlap(query: str, texts: list) -> list:
    """Order indexes by keyword overlap with the query (desc), ties by index.

    Pure ranking for context budgeting: highest query coverage first, stable
    original order on ties. Returns original indexes, highest-ranked first.
    """
    q = _tokens(query or "")
    scored = []
    for i, text in enumerate(texts or []):
        toks = _tokens(text or "")
        overlap = len(q & toks) / len(q) if q and toks else 0.0
        scored.append((overlap, i))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [i for _, i in scored]


def assess(claims: list, evidence: list) -> list:
    """Assess each claim against evidence. Pure function."""
    out: list = []
    for claim in claims:
        score, matched = score_claim(claim, evidence)
        verdict = _verdict(score)
        if verdict is Verdict.SUPPORTED:
            rationale = "Evidence matches most key words."
        elif verdict is Verdict.CONTESTED:
            rationale = "Only some key words match. A person should review this."
        else:
            rationale = "No evidence lines share enough key words with this claim."
        out.append(
            Assessment(
                claim=claim,
                verdict=verdict,
                score=score,
                rationale=rationale,
                evidence_ids=matched,
                uncertainty=uncertainty_for(verdict, False),
            )
        )
    return out


def uncertainty_for(verdict: Verdict, contradicted: bool) -> str:
    """Map verdict (+contradiction flag) to low/medium/high uncertainty."""
    if verdict is Verdict.UNSUPPORTED:
        return "high"
    if verdict is Verdict.CONTESTED or contradicted:
        return "medium"
    return "low"


def fallback_unverified(claims: list, reason: str,
                        method: str = "live fallback: unverified (not a live judgment)") -> list:
    """Deterministic fallback when a live verdict cannot be produced.

    Returns one UNSUPPORTED, zero-citation assessment per claim. The
    rationale names the missing provenance; the method forbids reading the
    finding as a verified live judgment or as proof of falsehood. Pure.
    """
    why = (reason or "provenance unavailable").strip().rstrip(".")
    return [
        Assessment(
            claim=claim, verdict=Verdict.UNSUPPORTED, score=0.0,
            rationale=f"UNVERIFIED. {why}. No live verdict was produced.",
            evidence_ids=(), uncertainty="high", method=method,
        )
        for claim in (claims or [])
    ]


def find_contradictions(evidence: list) -> list:
    """Flag evidence pairs sharing subject terms where exactly one is negated.

    Heuristic only: returns [(id_a, id_b, shared_terms)] for human review.
    """
    token_sets = {ev.id: _tokens(ev.text) for ev in evidence}
    negated = {ev.id: bool(_WORD.findall(ev.text.lower()) and
                           set(_WORD.findall(ev.text.lower())) & NEGATIONS)
               for ev in evidence}
    pairs: list = []
    ids = [ev.id for ev in evidence]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            shared = sorted(token_sets[ids[i]] & token_sets[ids[j]] - NEGATIONS)
            if len(shared) >= 2 and negated[ids[i]] != negated[ids[j]]:
                pairs.append((ids[i], ids[j], tuple(shared)))
    return pairs


def annotate_contradictions(assessments: list, evidence: list) -> list:
    """Return copies of assessments with contradicted_by + uncertainty updated."""
    pairs = find_contradictions(evidence)
    tension: dict = {}
    for a, b, _ in pairs:
        tension.setdefault(a, set()).add(b)
        tension.setdefault(b, set()).add(a)
    out: list = []
    for assessment in assessments:
        others: set = set()
        for eid in assessment.evidence_ids:
            others |= tension.get(eid, set())
        out.append(
            Assessment(
                claim=assessment.claim,
                verdict=assessment.verdict,
                score=assessment.score,
                rationale=assessment.rationale,
                evidence_ids=assessment.evidence_ids,
                uncertainty=uncertainty_for(assessment.verdict, bool(others)),
                contradicted_by=tuple(sorted(others)),
                method=assessment.method,
            )
        )
    return out

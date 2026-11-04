"""Visa Document Readiness Review helpers. Pure functions, no Streamlit import."""
from __future__ import annotations

from pruvcore.schemas import Verdict

READY = "Ready for review"
NEEDS_ATTENTION = "Needs attention"
MISSING = "Missing evidence"

SAFETY_NOTE = (
    "Readiness is not approval. This review checks whether each item has "
    "supporting evidence on file. It does not decide visa eligibility, and it "
    "does not replace official government instructions or advice from an "
    "immigration professional. Always verify requirements against the "
    "official source named in this review."
)

COVERAGE_HELP = (
    "Ready for review means evidence is present for review. It does not mean "
    "the application meets legal requirements or will be approved. Needs "
    "attention means the evidence only partly matches. Missing evidence "
    "means no matching evidence was found, so the item is uncertain, not "
    "verified."
)

_COVERAGE = {Verdict.SUPPORTED: READY, Verdict.CONTESTED: NEEDS_ATTENTION,
             Verdict.UNSUPPORTED: MISSING}


def coverage_for(verdict: Verdict | str) -> str:
    """Map one verdict to its coverage label. Unknown input stays Missing."""
    if isinstance(verdict, Verdict):
        return _COVERAGE[verdict]
    try:
        return _COVERAGE[Verdict(str(verdict or "").strip().lower())]
    except ValueError:
        return MISSING


def coverage_summary(assessments: list) -> dict:
    """Count assessments by coverage label."""
    summary = {"ready": 0, "needs_attention": 0, "missing": 0}
    for item in assessments or []:
        label = coverage_for(item.verdict)
        if label == READY:
            summary["ready"] += 1
        elif label == NEEDS_ATTENTION:
            summary["needs_attention"] += 1
        else:
            summary["missing"] += 1
    summary["total"] = summary["ready"] + summary["needs_attention"] + summary["missing"]
    return summary


def coverage_line(summary: dict) -> str:
    """One line rollup of coverage counts."""
    summary = summary or {}
    return (f"{summary.get('ready', 0)} Ready for review / "
            f"{summary.get('needs_attention', 0)} Needs attention / "
            f"{summary.get('missing', 0)} Missing evidence ({summary.get('total', 0)} total)")

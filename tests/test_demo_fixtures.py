"""Demo fixtures produce the verdicts DEMO.md promises (mock scorer)."""
import json
import os

from pruvcore.pipeline import assess, extract_claims
from pruvcore.schemas import Claim, EvidenceRef, Verdict

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _load(name):
    with open(os.path.join(_FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_requirements_fixture_verdicts():
    data = _load("requirements_review.json")
    verdicts = []
    for i, item in enumerate(data["items"]):
        ev = [EvidenceRef(id=e["id"], text=e["text"]) for e in item["evidence"]]
        (result,) = assess([Claim(id=f"r{i + 1}", text=item["requirement"])], ev)
        verdicts.append(result.verdict)
    assert verdicts == [Verdict.SUPPORTED, Verdict.CONTESTED, Verdict.UNSUPPORTED]


def test_dispute_fixture_flips_by_side():
    data = _load("business_dispute.json")
    claim = Claim(id="d1", text=data["claim"])
    side_a = [EvidenceRef(id=e["id"], text=e["text"]) for e in data["side_a"]["evidence"]]
    side_b = [EvidenceRef(id=e["id"], text=e["text"]) for e in data["side_b"]["evidence"]]
    assert assess([claim], side_a)[0].verdict is Verdict.SUPPORTED
    assert assess([claim], side_b)[0].verdict is Verdict.CONTESTED


def test_custom_fixture_verdicts():
    data = _load("custom_assessment.json")
    claims = [Claim(id=f"k{i + 1}", text=t) for i, t in enumerate(data["claims"])]
    ev = [EvidenceRef(id=e["id"], text=e["text"]) for e in data["evidence"]]
    assert [r.verdict for r in assess(claims, ev)] == [Verdict.SUPPORTED, Verdict.UNSUPPORTED]

"""Core schemas. 3.12-compatible stdlib only (dataclasses + enums)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    SUPPORTED = "supported"
    CONTESTED = "contested"
    UNSUPPORTED = "unsupported"


class Mode(str, Enum):
    REQUIREMENTS = "requirements"
    DISPUTES = "disputes"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Document:
    text: str
    source: str = "text"
    mode: Mode = Mode.CUSTOM


@dataclass(frozen=True)
class Claim:
    id: str
    text: str


@dataclass(frozen=True)
class EvidenceRef:
    id: str
    text: str
    source: str = "user"
    locator: str = ""  # exact reference, e.g. "upload:notes.txt" or "url:https://…"


@dataclass(frozen=True)
class Assessment:
    claim: Claim
    verdict: Verdict
    score: float  # 0.0..1.0 keyword-overlap heuristic (NOT an AI judgment)
    rationale: str
    evidence_ids: tuple = field(default_factory=tuple)
    uncertainty: str = "medium"  # low | medium | high
    contradicted_by: tuple = field(default_factory=tuple)  # evidence ids in tension
    method: str = "keyword-overlap heuristic (not an AI judgment)"

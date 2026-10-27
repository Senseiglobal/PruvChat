"""Deterministic mock Meta provider. No network, no secrets, no randomness."""
from __future__ import annotations


class MockMetaProvider:
    """Canned verdicts from prompt keywords; records every call for tests."""

    model = "mock-meta-1"

    def __init__(self) -> None:
        self.calls: list = []

    def generate(self, prompt: str) -> dict:
        text = (prompt or "").strip()
        self.calls.append(text)
        low = text.lower()
        if not low:
            return {"verdict": "unsupported", "rationale": "Empty prompt; nothing to assess.", "model": self.model}
        if "contradict" in low or "dispute" in low or "conflict" in low:
            return {"verdict": "contested", "rationale": "Mock: prompt signals disagreement.", "model": self.model}
        if "verify" in low or "confirm" in low or "evidence" in low:
            return {"verdict": "supported", "rationale": "Mock: prompt cites supporting evidence.", "model": self.model}
        return {"verdict": "unsupported", "rationale": "Mock: no supporting signal in prompt.", "model": self.model}

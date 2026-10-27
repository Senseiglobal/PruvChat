"""Mock Meta provider: deterministic canned verdicts, call recording."""
from providers.meta_mock import MockMetaProvider


def test_provider_deterministic_and_records_calls():
    p = MockMetaProvider()
    first = p.generate("Please verify this claim against the evidence.")
    assert p.generate("Please verify this claim against the evidence.") == first
    assert first["verdict"] == "supported"
    assert first["model"] == "mock-meta-1"
    assert len(p.calls) == 2


def test_provider_empty_dispute_and_plain_prompts():
    p = MockMetaProvider()
    assert p.generate("   ")["verdict"] == "unsupported"
    assert p.generate("The sides contradict each other.")["verdict"] == "contested"
    assert p.generate("Just a plain sentence.")["verdict"] == "unsupported"

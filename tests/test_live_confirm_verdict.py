"""Live blank-verdict regression: Custom review, one claim, mocked Meta API.

Reproduces the observed bug: Live engine, model muse-spark-1.3, one claim
plus supporting evidence, Confirm & run live clicked. The run is billed
(usage recorded) and the progress bar completes, but no verdict card,
finding, or error appears in the SAME run, and the confirmation panel
stays visible.

No network, no paid calls: the Meta transport is stubbed at urlopen and
returns the fixed usage from the report (191 in / 187 out tokens).
"""
import io
import json

import providers.meta_live as live_mod
from test_save_interaction import FakeSt, _run_app_script


def _resp(payload: dict):
    body = json.dumps(payload).encode()

    class FakeResp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return FakeResp(body)


def _grounded_payload(verdict="supported", cited=(0,)):
    return {
        "choices": [{
            "message": {"content": json.dumps(
                {"verdict": verdict, "rationale": "Span matches exactly.",
                 "cited": list(cited)})},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 191, "completion_tokens": 187},
    }


def _live_session():
    return {"nav": "Custom review", "engine": "Live Meta API (billed)",
            "live_model": "muse-spark-1.3",
            "c_obj": "Verify the claims below against the evidence.",
            "c_claims": "The beta test passed on Friday.",
            "c_ev": "The beta test passed on Friday with no blockers."}


def test_live_custom_confirm_renders_verdict_same_run(tmp_path, monkeypatch):
    """Confirm run must stash, render verdict, show usage, clear pending."""
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    (tmp_path / ".env").write_text("MODEL_API_KEY=fake-test-key\n", encoding="utf-8")
    monkeypatch.setattr(live_mod, "urlopen",
                        lambda *a, **k: _resp(_grounded_payload()))

    fake = FakeSt()
    fake.session_state.update(_live_session())

    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    assert "custom" in fake.session_state.get("live_pending", {})
    assert "results_custom" not in fake.session_state

    fake.script = {"confirm_custom": True}
    fake.calls.clear()
    fake.errors_shown.clear()
    try:
        _run_app_script(fake, tmp_path)
    except Exception as exc:
        assert type(exc).__name__ == "FakeRerun", f"confirm crashed: {exc!r}"

    assert "results_custom" in fake.session_state, "live response was lost, not stashed"
    job = fake.session_state["results_custom"]
    assert [a.verdict.value for a in job["results"]] == ["supported"]
    assert job["results"][0].evidence_ids == ("e1",)

    spend = fake.session_state.get("live_spend", {})
    assert spend.get("calls") == 1
    assert spend.get("usd", 0) > 0
    assert any(c[0] == "caption" and "Live usage this run: 191 in / 187 out" in str(c[1])
               for c in fake.calls), "usage caption missing or wrong"

    assert any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fake.calls), \
        "no LIVE verdict banner in the confirm run"
    assert any(c[0] == "subheader" and "SUPPORTED" in str(c[1]) for c in fake.calls), \
        "no finding card in the confirm run"

    assert fake.session_state.get("live_pending", {}) == {}, "pending not cleared"
    calls_before = spend.get("calls")
    fake.script = {"confirm_custom": True}
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert fake.session_state.get("live_spend", {}).get("calls") == calls_before, \
        "stale confirm click caused a duplicate paid call"
    assert any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fake.calls), \
        "verdict lost on the follow-up rerun"


def test_live_custom_failure_shows_error_and_unverified(tmp_path, monkeypatch):
    """A failed live call must show an error plus UNVERIFIED, never blank."""
    from urllib.error import HTTPError

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    (tmp_path / ".env").write_text("MODEL_API_KEY=fake-test-key\n", encoding="utf-8")
    err = HTTPError("https://api.meta.ai/v1/chat/completions", 429, "err", {},
                    io.BytesIO(json.dumps({"error": {"message": "slow down"}}).encode()))
    monkeypatch.setattr(live_mod, "urlopen", lambda *a, **k: (_ for _ in ()).throw(err))

    fake = FakeSt()
    fake.session_state.update(_live_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)

    fake.script = {"confirm_custom": True}
    fake.calls.clear()
    fake.errors_shown.clear()
    try:
        _run_app_script(fake, tmp_path)
    except Exception as exc:
        assert type(exc).__name__ == "FakeRerun", f"confirm crashed: {exc!r}"

    assert any("Recorded as UNVERIFIED" in e for e in fake.errors_shown), \
        "failure must show a visible error"
    assert "results_custom" in fake.session_state, "failure must stash UNVERIFIED fallback"
    job = fake.session_state["results_custom"]
    assert job["results"][0].rationale.startswith("UNVERIFIED")
    assert fake.session_state.get("live_pending", {}) == {}

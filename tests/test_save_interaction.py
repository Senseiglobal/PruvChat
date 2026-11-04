"""End-to-end save interaction: execute the REAL app.py across scripted reruns.

A scripted fake of the Streamlit API reproduces rerun semantics (buttons True
for exactly one run; widget values persist in session state) and runs the
actual application script twice: first a Run click, then a Save click. This
is the regression net for save-button bugs that storage unit tests cannot see.
"""
import os
import sys

import pytest

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


class FakeRerun(Exception):
    pass


class _Dummy:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeSt:
    """Minimal scripted stand-in for the streamlit module."""

    def __init__(self):
        self.session_state = {}
        self.script = {}
        self.calls = []
        self.errors_shown = []
        self.choices = {}
        self.helps = {}

    @property
    def sidebar(self):
        return self

    def button(self, label, key=None, **kw):
        self.calls.append(("button", label, key, kw.get("type", "secondary")))
        if kw.get("help"):
            self.helps[("button", key if key is not None else label)] = kw["help"]
        if key is not None:
            return bool(self.script.get(key, False))
        return bool(self.script.get(label, False))

    def _choosing_widget(self, name, label, options, key, default=0, help=None):
        self.calls.append((name, label, key))
        if help:
            self.helps[(name, key if key is not None else label)] = help
        self.choices[(name, key if key is not None else label)] = list(options)
        opts = list(options)
        if key is not None:
            return self.session_state.setdefault(key, opts[default] if opts else None)
        return opts[default] if opts else None

    def radio(self, label, options, key=None, **kw):
        return self._choosing_widget("radio", label, options, key, help=kw.get("help"))

    def selectbox(self, label, options, key=None, **kw):
        return self._choosing_widget("selectbox", label, options, key, help=kw.get("help"))

    def _text_widget(self, name, label, value="", key=None, **kw):
        self.calls.append((name, label, key))
        if kw.get("help"):
            self.helps[(name, key if key is not None else label)] = kw["help"]
        if key is not None:
            return self.session_state.setdefault(key, value)
        return value

    def text_input(self, label, value="", key=None, **kw):
        return self._text_widget("text_input", label, value, key, help=kw.get("help"))

    def text_area(self, label, value="", key=None, **kw):
        return self._text_widget("text_area", label, value, key, help=kw.get("help"))

    def checkbox(self, label, value=False, key=None, **kw):
        self.calls.append(("checkbox", label, key))
        if key is not None:
            return self.session_state.setdefault(key, value)
        return value

    def file_uploader(self, *a, **kw):
        self.calls.append(("file_uploader",))
        return None

    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return tuple(_Dummy() for _ in range(n))

    def container(self, *a, **kw):
        return _Dummy()

    def expander(self, *a, **kw):
        return _Dummy()

    def popover(self, label, **kw):
        self.calls.append(("popover", label, kw))
        return _Dummy()

    def spinner(self, *a, **kw):
        return _Dummy()

    def status(self, *a, **kw):
        return _Dummy()

    def progress(self, *a, **kw):
        return _Dummy()

    def rerun(self):
        raise FakeRerun()

    def __getattr__(self, name):
        def _rec(*a, **kw):
            self.calls.append((name, a, kw))
            if name == "error" and a:
                self.errors_shown.append(str(a[0]))
            return None

        return _rec


def _run_app_script(fake, tmp_path):
    """Execute the real app.py with the fake streamlit module and tmp project dir."""
    with open(APP_PATH, encoding="utf-8") as fh:
        src = fh.read()
    namespace = {"__file__": str(tmp_path / "app.py"), "__name__": "__main__"}
    sys.modules["streamlit"] = fake
    try:
        exec(compile(src, str(tmp_path / "app.py"), "exec"), namespace)  # noqa: S102
    finally:
        del sys.modules["streamlit"]


def _fresh_session():
    return {"nav": "Requirements", "engine": "Mock (offline, free)",
            "req_text": "Alpha beta gamma.", "req_ev": "Alpha beta gamma delta"}


def test_run_then_save_click_persists_and_lists(tmp_path):
    from pruvcore.store import list_runs, load_run

    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    # Rerun 1: user clicks Run assessment.
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    assert "results_requirements" in fake.session_state
    assert fake.errors_shown == []
    # Rerun 2: user names the workspace and clicks Save.
    fake.session_state["save_name_requirements"] = "PruvChat-Test-01"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert any(c[0] == "success" and "Saved successfully." in str(c[1])
               for c in fake.calls)
    assert not any(c[0] == "success" and ".json" in str(c[1]) for c in fake.calls)
    assert fake.errors_shown == []
    runs = list_runs(str(tmp_path))
    assert [r["name"] for r in runs] == ["PruvChat-Test-01"]
    assert load_run(str(tmp_path), runs[0]["file"])["inputs"]["requirements"] == "Alpha beta gamma."
    status = fake.session_state.get("save_status_requirements")
    assert status and status["ok"] is True and "PruvChat-Test-01" in status["message"]
    trace = (tmp_path / ".pruvchat_runs" / "save_trace.log").read_text(encoding="utf-8")
    assert "mode=requirements" in trace and "name=PruvChat-Test-01" in trace and " OK " in trace
    # Rerun 3: post-save render still shows the Save section (no vanishing UI).
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert ("button", "Save workspace locally", "save_requirements",
            "secondary") in fake.calls
    assert fake.errors_shown == []
    assert any(c[0] == "info" and "Last save" in str(c[1]) for c in fake.calls)


def test_save_failure_shows_persistent_error_and_trace(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    project = blocker / "app.py"  # dirname is a file: runs dir cannot be created
    fake = FakeSt()
    fake.session_state.update(_fresh_session())

    def _run_blocked():
        with open(APP_PATH, encoding="utf-8") as fh:
            src = fh.read()
        namespace = {"__file__": str(project), "__name__": "__main__"}
        sys.modules["streamlit"] = fake
        try:
            exec(compile(src, str(project), "exec"), namespace)  # noqa: S102
        finally:
            del sys.modules["streamlit"]

    fake.script = {"Run assessment": True}
    _run_blocked()
    assert "results_requirements" in fake.session_state
    fake.session_state["save_name_requirements"] = "wont-save"
    fake.script = {"save_requirements": True}
    _run_blocked()  # error path must not raise or rerun
    status = fake.session_state.get("save_status_requirements")
    assert status and status["ok"] is False and status["message"]
    assert fake.errors_shown, "user must see the failure, not silence"
    assert any("Could not save" in e for e in fake.errors_shown)
    # Trace is best-effort: unwritable location means no log, but no crash either.


def test_open_after_restart_renders_saved_findings(tmp_path):
    from pruvcore.store import list_runs

    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_requirements"] = "keep-me"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert len(list_runs(str(tmp_path))) == 1
    # Simulate a Streamlit restart: brand-new session, same project dir.
    fresh = FakeSt()
    fresh.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    assert fresh.session_state["req_text"] == "Alpha beta gamma."
    assert "results_requirements" in fresh.session_state
    fresh.script = {}
    fresh.calls.clear()
    _run_app_script(fresh, tmp_path)  # rerun renders with zero clicks
    assert "results_requirements" in fresh.session_state
    assert any(c[0] == "info" and "Restored saved findings" in str(c[1]) for c in fresh.calls)
    assert any(c[0] == "subheader" for c in fresh.calls)
    assert any(c[0] == "download_button" for c in fresh.calls)
    assert fresh.errors_shown == []


def test_open_live_restore_calls_no_provider(tmp_path, monkeypatch):
    import json as _json
    from pruvcore.pipeline import assess as _assess
    from pruvcore.schemas import Claim as _Claim, EvidenceRef as _Ev
    from pruvcards.render import assessment_to_card as _card
    from pruvcore.store import save_run as _save

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    (a,) = _assess([_Claim(id="k1", text="Alpha beta")],
                   [_Ev(id="e1", text="Alpha beta", source="s", locator="L")])
    card = _card(a, {"e1": _Ev(id="e1", text="Alpha beta", source="s", locator="L")})
    _save(str(tmp_path), "live-run", "custom", {"objective": "o", "claims": "Alpha beta",
           "evidence": "Alpha beta"}, [card], {"supported": 1, "total": 1},
           engine="live", provider="meta-live", model="muse-spark-1.3")
    fake = FakeSt()  # mock engine, no key anywhere
    fake.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "info" and "Restored saved findings" in str(c[1]) for c in fake.calls)
    assert fake.errors_shown == []


def test_open_legacy_restores_inputs_with_notice(tmp_path):
    runs_dir = tmp_path / ".pruvchat_runs"
    runs_dir.mkdir()
    import json as _json
    (runs_dir / "old.json").write_text(_json.dumps(
        {"name": "old", "mode": "custom", "inputs": {"claims": "legacy claim"}}), encoding="utf-8")
    fake = FakeSt()
    fake.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state.get("c_claims") == "legacy claim"
    assert "results_custom" not in fake.session_state
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "info" and "No saved assessment results" in str(c[1]) for c in fake.calls)
    assert fake.errors_shown == []


def test_open_unknown_mode_fails_gracefully(tmp_path):
    from pruvcore.store import save_run as _save

    _save(str(tmp_path), "weird", "weird-mode", {"a": "b"}, [], {"total": 0})
    fake = FakeSt()
    fake.script = {"open_btn": True}
    _run_app_script(fake, tmp_path)  # no rerun: handler raised before it
    assert any("Could not open" in e for e in fake.errors_shown)
    assert fake.session_state.get("nav", "Overview") == "Overview"


def test_save_without_prior_run_writes_nothing(tmp_path):
    from pruvcore.store import list_runs

    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.script = {"save_requirements": True}
    _run_app_script(fake, tmp_path)  # no results stashed: no save section, no crash
    assert ("button", "Save workspace locally", "save_requirements",
            "secondary") not in fake.calls
    assert list_runs(str(tmp_path)) == []


_FETCH_BODY = b"Alpha beta gamma delta.\nSecond fetched line here."


def _mock_public_web(monkeypatch, body=_FETCH_BODY, ctype="text/plain"):
    """Fake DNS (public IP) + fake HTTP opener. No sockets, no real sites.

    Returns an opener-call counter so tests can prove later reruns
    perform zero network I/O.
    """
    import socket

    import pruvfetch.fetch as fetch_mod
    from test_fetch import FakeResp

    stats = {"opens": 0}

    def fake_getaddrinfo(host, port, type=None, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    class _Opener:
        addheaders = []

        def open(self, req, timeout=None):
            stats["opens"] += 1
            return FakeResp(body, ctype=ctype)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(fetch_mod, "build_opener", lambda *a: _Opener())
    return stats


def _forbid_live_provider(monkeypatch):
    """Fail if app code instantiates any provider (mock-mode fetch tests)."""
    import providers

    def _guard(mode, *a, **k):
        raise AssertionError(f"provider {mode!r} must not be used in mock fetch tests")

    monkeypatch.setattr(providers, "get_provider", _guard)


def _fetch_session():
    return {"nav": "Requirements", "engine": "Mock (offline, free)",
            "req_text": "Alpha beta gamma.", "req_ev": "zzz qqq unrelated",
            "url_req": "https://example.com/spec"}


def test_fetch_then_run_includes_url_evidence(tmp_path, monkeypatch):
    from pruvcards.render import assessment_to_card

    stats = _mock_public_web(monkeypatch)
    _forbid_live_provider(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    # Rerun 1: Fetch click stashes the document (button True for one run only).
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    assert "fetched_req" in fake.session_state
    assert fake.errors_shown == []
    # Rerun 2: separate Run click must still see the fetched evidence.
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    assert stats["opens"] == 1, "Run rerun must not refetch"
    job = fake.session_state["results_requirements"]
    url_refs = [e for e in job["evidence"] if e.source == "url"]
    assert [e.id for e in url_refs] == ["w1", "w2"]
    assert url_refs[0].locator == "url:https://example.com/spec"
    assert [a.verdict.value for a in job["results"]] == ["supported"]
    assert "w1" in job["results"][0].evidence_ids
    card = assessment_to_card(job["results"][0], {e.id: e for e in job["evidence"]})
    assert card["citations"][0]["excerpt"] == "Alpha beta gamma delta."
    assert card["citations"][0]["locator"] == "url:https://example.com/spec"
    assert any(c[0] == "caption" and "attached as evidence" in str(c[1]) for c in fake.calls)
    assert "live_pending" not in fake.session_state
    assert fake.errors_shown == []


def test_fetch_unchecked_excludes_url_evidence(tmp_path, monkeypatch):
    _mock_public_web(monkeypatch)
    _forbid_live_provider(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    assert "fetched_req" in fake.session_state
    fake.session_state["use_req"] = False
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state["results_requirements"]
    assert [e for e in job["evidence"] if e.source == "url"] == []
    assert [a.verdict.value for a in job["results"]] == ["unsupported"]
    assert any(c[0] == "caption" and "excluded from the assessment" in str(c[1])
               for c in fake.calls)
    # NB: the UNSUPPORTED status badge itself uses st.error; only fetch/save
    # failures count as real errors here.
    assert not any("blocked or failed" in e or "Could not" in e for e in fake.errors_shown)


def test_fetch_blocked_shows_error_and_clears_stash(tmp_path, monkeypatch):
    _mock_public_web(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    assert "fetched_req" in fake.session_state
    # A later blocked fetch must not leave the stale good document attached.
    fake.session_state["url_req"] = "http://127.0.0.1/secret"
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    assert "fetched_req" not in fake.session_state
    assert any("Fetch blocked or failed" in e for e in fake.errors_shown)
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state["results_requirements"]
    assert [e for e in job["evidence"] if e.source == "url"] == []


def test_saved_workspace_preserves_fetched_provenance(tmp_path, monkeypatch):
    from pruvcards.render import assessments_to_markdown
    from pruvcore.store import export_report, list_runs, load_run

    _mock_public_web(monkeypatch)
    _forbid_live_provider(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_requirements"] = "fetch-provenance"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    data = load_run(str(tmp_path), list_runs(str(tmp_path))[0]["file"])
    assert "https://example.com/spec" in export_report(data)
    fresh = FakeSt()
    fresh.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    fresh.script = {}
    _run_app_script(fresh, tmp_path)
    job = fresh.session_state["results_requirements"]
    url_refs = [e for e in job["evidence"] if e.source == "url"]
    assert url_refs and url_refs[0].locator == "url:https://example.com/spec"
    by_id = {e.id: e for e in job["evidence"]}
    assert "Alpha beta gamma delta." in assessments_to_markdown(job["results"], by_id)
    assert any(c[0] == "info" and "Restored saved findings" in str(c[1]) for c in fresh.calls)
    assert fresh.errors_shown == []


def test_changed_url_detaches_stale_fetch(tmp_path, monkeypatch):
    _mock_public_web(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["url_req"] = "https://example.com/other"
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state["results_requirements"]
    assert [e for e in job["evidence"] if e.source == "url"] == []
    assert any(c[0] == "caption" and "click Fetch again" in str(c[1]) for c in fake.calls)


_LIVE_MODES = {
    "requirements": {
        "nav": "Requirements",
        "inputs": {"req_text": "Alpha beta.", "req_ev": "Alpha beta gamma"},
        "no_evidence": {"req_text": "Alpha beta.", "req_ev": ""},
        "locator": "pasted text #1",
        "confirm": "confirm_requirements",
        "results": "results_requirements",
    },
    "disputes": {
        "nav": "Business disputes",
        "inputs": {"d_claim": "Alpha beta.", "d_a": "Alpha beta gamma", "d_b": "zzz qqq"},
        "no_evidence": {"d_claim": "Alpha beta.", "d_a": "", "d_b": ""},
        "locator": "side A #1",
        "confirm": "confirm_disputes-a",
        "results": "results_disputes-a",
    },
    "custom": {
        "nav": "Custom review",
        "inputs": {"c_obj": "o", "c_claims": "Alpha beta.", "c_ev": "Alpha beta gamma"},
        "no_evidence": {"c_obj": "o", "c_claims": "Alpha beta.", "c_ev": ""},
        "locator": "pasted text #1",
        "confirm": "confirm_custom",
        "results": "results_custom",
    },
}


class _FakeLiveProvider:
    """Scripted stand-in for MetaLiveProvider. No network, no key."""

    model = "fake-live-1"

    def __init__(self, script):
        self._script = script  # claim text -> result dict or Exception; "*" is default
        self.calls = []
        self.usage_total = {"input_tokens": 0, "output_tokens": 0}
        self.last_diagnostics = {}

    def assess_claim(self, claim_text, evidence_texts):
        outcome = self._script.get(claim_text, self._script.get("*"))
        if isinstance(outcome, Exception):
            raise outcome
        self.calls.append(claim_text)
        return outcome

    def estimated_cost_usd(self):
        return 0.0


def _patch_live_provider(monkeypatch, script):
    import providers

    fake = _FakeLiveProvider(script)
    monkeypatch.setattr(providers, "get_provider", lambda mode, **k: fake)
    return fake


def _live_session(cfg, inputs):
    session = {"nav": cfg["nav"], "engine": "Live Meta API (billed)"}
    session.update(inputs)
    return session


def _no_keys(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)


def _live_out(verdict, cited):
    return {"verdict": verdict, "rationale": f"{verdict} per span", "cited": cited,
            "model": "fake-live-1", "usage": {"input_tokens": 10, "output_tokens": 5}}


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_missing_evidence_falls_back_unverified(tmp_path, monkeypatch, mode):
    cfg = _LIVE_MODES[mode]
    _no_keys(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, cfg["no_evidence"]))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    assert fake.session_state.get("live_pending", {}) == {}, "nothing may stage"
    job = fake.session_state[cfg["results"]]
    assert job["engine"] == "Mock (offline, free)" and job["fallback"] is True
    assert job["live_label"] is None
    (finding,) = job["results"]
    assert finding.verdict.value == "unsupported" and finding.evidence_ids == ()
    assert finding.rationale.startswith("UNVERIFIED") and "no evidence supplied" in finding.rationale
    assert finding.method.startswith("live fallback")
    assert any(c[0] == "warning" and "UNVERIFIED placeholders" in str(c[1]) for c in fake.calls)
    assert not any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_valid_citations_preserved_exactly(tmp_path, monkeypatch, mode):
    from pruvcards.render import assessment_to_card

    cfg = _LIVE_MODES[mode]
    _no_keys(monkeypatch)
    provider = _patch_live_provider(monkeypatch, {"*": _live_out("supported", (0,))})
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, cfg["inputs"]))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)  # stages pending; no provider call yet
    assert provider.calls == []
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    assert provider.calls != []
    job = fake.session_state[cfg["results"]]
    (finding,) = job["results"]
    assert finding.verdict.value == "supported" and finding.method.startswith("live Meta API")
    by_id = {e.id: e for e in job["evidence"]}
    (eid,) = finding.evidence_ids
    assert by_id[eid].text == "Alpha beta gamma" and by_id[eid].locator == cfg["locator"]
    card = assessment_to_card(finding, by_id)
    assert card["citations"][0]["excerpt"] == "Alpha beta gamma"
    assert card["citations"][0]["locator"] == cfg["locator"]
    assert "0 unverified" in job["live_label"]
    fake.script = {}
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_missing_citations_downgraded_to_unverified(tmp_path, monkeypatch, mode):
    cfg = _LIVE_MODES[mode]
    _no_keys(monkeypatch)
    _patch_live_provider(monkeypatch, {"*": _live_out("supported", ())})
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, cfg["inputs"]))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state[cfg["results"]]
    (finding,) = job["results"]
    assert finding.verdict.value == "unsupported" and finding.evidence_ids == ()
    assert finding.rationale.startswith("UNVERIFIED") and "zero citations" in finding.rationale
    assert finding.method == "live fallback: unverified (no citable evidence)"
    assert any(c[0] == "warning" and "zero citations" in str(c[1]) for c in fake.calls)
    assert "1 unverified" in job["live_label"]


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_invalid_citation_id_recorded_unverified(tmp_path, monkeypatch, mode):
    from providers.meta_live import ProviderError

    cfg = _LIVE_MODES[mode]
    _no_keys(monkeypatch)
    _patch_live_provider(monkeypatch, {"*": ProviderError("Meta API cited out-of-range evidence [9]")})
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, cfg["inputs"]))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state[cfg["results"]]
    (finding,) = job["results"]
    assert finding.verdict.value == "unsupported" and finding.evidence_ids == ()
    assert finding.rationale.startswith("UNVERIFIED") and "out-of-range" in finding.rationale
    assert any("Recorded as UNVERIFIED" in e for e in fake.errors_shown)
    assert "1 unverified" in job["live_label"] and "1 error(s)" in job["live_label"]
    assert fake.session_state["live_spend"]["calls"] == 0


def test_live_unsupported_without_citations_is_coherent(tmp_path, monkeypatch):
    # unsupported + zero citations is a genuine live judgment (nothing supports
    # the claim), so it must NOT be downgraded to a fallback.
    cfg = _LIVE_MODES["custom"]
    _no_keys(monkeypatch)
    _patch_live_provider(monkeypatch, {
        "Alpha beta.": _live_out("supported", (0,)),
        "Zebra quasar.": _live_out("unsupported", ())})
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, {"c_obj": "o", "c_claims": "Alpha beta.\nZebra quasar.",
                                                  "c_ev": "Alpha beta gamma"}))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state[cfg["results"]]
    assert [a.verdict.value for a in job["results"]] == ["supported", "unsupported"]
    assert job["results"][0].evidence_ids != ()
    assert job["results"][1].evidence_ids == ()
    assert job["results"][1].method.startswith("live Meta API")
    assert "0 unverified" in job["live_label"]


def test_fallback_save_restore_stays_mock_labeled(tmp_path, monkeypatch):
    from pruvcore.store import export_report, list_runs, load_run

    cfg = _LIVE_MODES["requirements"]
    _no_keys(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, cfg["no_evidence"]))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_requirements"] = "fallback-ws"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    data = load_run(str(tmp_path), list_runs(str(tmp_path))[0]["file"])
    assert data["engine"] == "mock" and data["provider"] == "mock"
    assert "UNVERIFIED" in export_report(data)
    fresh = FakeSt()
    fresh.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    fresh.script = {}
    _run_app_script(fresh, tmp_path)
    job = fresh.session_state["results_requirements"]
    assert "UNVERIFIED" in job["results"][0].rationale
    assert not any(c[0] == "info" and "LIVE verdicts" in str(c[1]) for c in fresh.calls)


def test_mock_engine_is_default(tmp_path):
    fake = FakeSt()
    _run_app_script(fake, tmp_path)
    assert fake.session_state["engine"] == "Mock (offline, free)"


def _stub_live_transport(monkeypatch, cited, verdict="supported"):
    """Stub HTTPS for the REAL provider: capture the prompt, script citations."""
    import io as _io
    import json as _json

    import providers.meta_live as live_mod

    seen = {}
    content = _json.dumps({"verdict": verdict, "rationale": "span matches exactly",
                           "cited": list(cited)})

    class FakeResp(_io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        payload = _json.loads(req.data.decode())
        seen["prompt"] = payload["messages"][1]["content"]
        body = _json.dumps({"choices": [{"message": {"content": content}}],
                            "usage": {"prompt_tokens": 60, "completion_tokens": 12}})
        return FakeResp(body.encode())

    monkeypatch.setattr(live_mod, "urlopen", fake_urlopen)
    return seen


def _grounding_inputs(mode):
    filler = [f"filler padding line {n} about weather and transit" for n in range(40)]
    filler[30] = "Alpha beta decisive span here"
    blob = "\n".join(filler)
    if mode == "requirements":
        return {"req_text": "Alpha beta.", "req_ev": blob}
    if mode == "disputes":
        return {"d_claim": "Alpha beta.", "d_a": blob, "d_b": "zzz qqq"}
    return {"c_obj": "o", "c_claims": "Alpha beta.", "c_ev": blob}


def _live_key(tmp_path, monkeypatch):
    _no_keys(monkeypatch)
    (tmp_path / ".env").write_text("MODEL_API_KEY=fake-test-key\n", encoding="utf-8")


_REL_ID = {"requirements": "e31", "disputes": "a31", "custom": "e31"}


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_grounding_reviews_relevant_item_past_twelve(tmp_path, monkeypatch, mode):
    cfg = _LIVE_MODES[mode]
    _live_key(tmp_path, monkeypatch)
    seen = _stub_live_transport(monkeypatch, cited=[0])
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, _grounding_inputs(mode)))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    assert "[0] Alpha beta decisive span here" in seen["prompt"]
    job = fake.session_state[cfg["results"]]
    (finding,) = job["results"]
    assert finding.verdict.value == "supported"
    assert finding.evidence_ids == (_REL_ID[mode],)
    assert "grounded in 12 of 40 items" in finding.method
    assert "28 omitted" in finding.method and "0 shortened" in finding.method
    assert any(c[0] == "caption" and "reviewed 12 of 40" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_live_citation_beyond_sent_range_is_unverified(tmp_path, monkeypatch, mode):
    cfg = _LIVE_MODES[mode]
    _live_key(tmp_path, monkeypatch)
    _stub_live_transport(monkeypatch, cited=[15])  # < 40 items, but only 12 sent
    fake = FakeSt()
    fake.session_state.update(_live_session(cfg, _grounding_inputs(mode)))
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.script = {cfg["confirm"]: True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state[cfg["results"]]
    (finding,) = job["results"]
    assert finding.verdict.value == "unsupported" and finding.evidence_ids == ()
    assert finding.rationale.startswith("UNVERIFIED") and "out-of-range" in finding.rationale


_DL_MODES = {
    "requirements": {
        "nav": "Requirements", "page": "Requirements",
        "inputs": {"req_text": "Alpha beta.", "req_ev": "Alpha beta gamma"},
        "save_mode": "requirements",
        "save_inputs": {"requirements": "Alpha beta.", "evidence": "Alpha beta gamma"},
    },
    "disputes": {
        "nav": "Business disputes", "page": "Business disputes",
        "inputs": {"d_claim": "Alpha beta.", "d_a": "Alpha beta gamma", "d_b": "zzz qqq"},
        "save_mode": "disputes-a",
        "save_inputs": {"claim": "Alpha beta.", "side_a": "Alpha beta gamma"},
    },
    "custom": {
        "nav": "Custom review", "page": "Custom review",
        "inputs": {"c_obj": "o", "c_claims": "Alpha beta.", "c_ev": "Alpha beta gamma"},
        "save_mode": "custom",
        "save_inputs": {"objective": "o", "claims": "Alpha beta.",
                        "evidence": "Alpha beta gamma"},
    },
}


def _downloads(fake, label):
    """(data, file_name) pairs for every download_button with this label."""
    return [(c[1][1], c[2].get("file_name")) for c in fake.calls
            if c[0] == "download_button" and c[1][0] == label]


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_mock_downloads_carry_mode_engine_and_cards(tmp_path, mode):
    cfg = _DL_MODES[mode]
    fake = FakeSt()
    fake.session_state.update({"nav": cfg["nav"], "engine": "Mock (offline, free)",
                               **cfg["inputs"]})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    docs = _downloads(fake, "Download findings (.md)")
    assert docs, "findings download must render"
    for data, fname in docs:
        assert data.startswith(f"# PruvChat findings: {cfg['page']}")
        assert "Engine: Mock (offline, free)" in data
        assert "heuristic overlap" in data and "live Meta API verdict" not in data
        assert "Next action:" in data and "Uncertainty:" in data
        assert fname and "_mock_report.md" in fname
    full = _downloads(fake, "Download full report (.md)")
    assert full
    for data, fname in full:
        assert "- Engine: mock" in data and "heuristic overlap" in data
        assert fname and "_mock_full.md" in fname


def _live_card_dict():
    return {"title": "SUPPORTED: Alpha beta", "claim": "Alpha beta", "claim_id": "k1",
            "status": "supported", "score": 1.0,
            "method": "live Meta API (fake-live-1) — no overlap score",
            "rationale": "span matches exactly", "evidence_ids": ["e1"],
            "citations": [{"id": "e1", "source": "pasted", "locator": "pasted text #1",
                           "excerpt": "Alpha beta gamma"}],
            "contradicted_by": [], "uncertainty": "low",
            "next_action": "Keep the cited source on file; no further evidence needed."}


@pytest.mark.parametrize("mode", ["requirements", "disputes", "custom"])
def test_restored_live_downloads_keep_live_labels(tmp_path, mode):
    from pruvcore.store import save_run as _save

    cfg = _DL_MODES[mode]
    _save(str(tmp_path), "live-ws", cfg["save_mode"], dict(cfg["save_inputs"]),
          [_live_card_dict()], {"supported": 1, "contested": 0, "unsupported": 0, "total": 1},
          engine="live", provider="meta-live", model="fake-live-1")
    fake = FakeSt()
    fake.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    fake.script = {}
    _run_app_script(fake, tmp_path)  # renders restored results; no rerun, no providers
    docs = _downloads(fake, "Download findings (.md)")
    assert docs
    for data, fname in docs:
        assert "live Meta API verdict, no overlap score" in data
        assert "heuristic overlap" not in data
        assert "Engine: Live Meta API (billed)" in data
        assert "Restored:" in data and "fake-live-1" in data
        assert "Alpha beta gamma" in data and "pasted text #1" in data
        assert fname and "_live_report.md" in fname


def test_url_evidence_downloads_carry_provenance(tmp_path, monkeypatch):
    _mock_public_web(monkeypatch)
    fake = FakeSt()
    fake.session_state.update(_fetch_session())
    fake.script = {"fetch_req": True}
    _run_app_script(fake, tmp_path)
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    [(data, fname)] = _downloads(fake, "Download findings (.md)")
    assert "url:https://example.com/spec" in data
    assert "Alpha beta gamma delta." in data
    assert "Engine: Mock (offline, free)" in data
    assert fname and "_mock_report.md" in fname
    full = _downloads(fake, "Download full report (.md)")[0][0]
    assert "url:https://example.com/spec" in full and "Alpha beta gamma delta." in full


def test_white_theme_injected_with_no_switcher(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    _run_app_script(fake, tmp_path)
    assert "theme" not in fake.session_state
    assert ("radio", "theme") not in fake.choices
    assert any(c[0] == "markdown" and "pruvchat-theme:white" in str(c[1])
               for c in fake.calls)
    assert not any(c[0] == "caption" and "Using " in str(c[1]) and "theme" in str(c[1])
                   for c in fake.calls)
    fake.calls.clear()
    _run_app_script(fake, tmp_path)  # plain rerun keeps the same sheet
    assert any(c[0] == "markdown" and "pruvchat-theme:white" in str(c[1])
               for c in fake.calls)
    assert fake.session_state["nav"] == "Requirements"  # navigation intact


def test_injected_css_styles_toolbar_and_deploy(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    _run_app_script(fake, tmp_path)
    css_calls = [str(c[1]) for c in fake.calls
                 if c[0] == "markdown" and "pruvchat-theme:" in str(c[1])]
    assert css_calls
    for css in css_calls:
        assert "stAppDeployButton" in css and "stToolbar" in css
        assert "button:focus-visible" in css


def test_save_reload_roundtrip_keeps_white_theme(tmp_path):
    from pruvcore.store import list_runs

    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_requirements"] = "keep-ws"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert len(list_runs(str(tmp_path))) == 1
    fresh = FakeSt()
    fresh.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    assert "results_requirements" in fresh.session_state
    fresh.script = {}
    _run_app_script(fresh, tmp_path)
    assert any(c[0] == "subheader" for c in fresh.calls)
    assert any(c[0] == "markdown" and "pruvchat-theme:white" in str(c[1])
               for c in fresh.calls)


@pytest.mark.parametrize("mode", ["Requirements", "Business disputes", "Custom review",
                                 "Visa review"])
def test_mode_pages_have_try_example_and_no_back_button(tmp_path, mode):
    fake = FakeSt()
    fake.session_state.update({"nav": mode, "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    labels = [c[1] for c in fake.calls if c[0] == "button"
              and not str(c[2]).startswith("nav_")]
    assert "Try example" in labels
    assert "Load sample fixture" not in labels
    assert not any("Overview" in str(label) for label in labels)
    assert any(c[0] == "caption" and "synthetic demo data" in str(c[1]) for c in fake.calls)
    # The top menu is the way back (no duplicate back buttons in content).
    nav = [c[1] for c in fake.calls if c[0] == "button" and str(c[2]).startswith("nav_")]
    assert "Overview" in nav


def test_cards_render_all_verdict_types_with_text_labels(tmp_path):
    fake = FakeSt()
    fake.session_state.update({
        "nav": "Business disputes", "engine": "Mock (offline, free)",
        "d_claim": "Order 1042 arrived damaged and missing parts.",
        "d_a": "Order 1042 arrived with a cracked panel and missing screws.",
        "d_b": "Order 1042 passed warehouse inspection before shipping."})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = " ".join(str(c[1]) for c in fake.calls)
    assert "SUPPORTED" in texts and "CONTESTED" in texts  # text labels, both sides
    assert "Contradiction flag" in texts and "Uncertainty:" in texts
    assert "The evidence backs this claim." in texts
    fake.session_state.update({"nav": "Custom review", "c_obj": "o",
                               "c_claims": "Zebra quasar.", "c_ev": "unrelated lines here"})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = " ".join(str(c[1]) for c in fake.calls)
    assert "UNSUPPORTED" in texts and "No supporting evidence was found" in texts


def test_custom_claims_split_one_per_line(tmp_path):
    # Regression: the Custom page promises one claim per line, so lines
    # without sentence punctuation must still become separate claims.
    fake = FakeSt()
    fake.session_state.update({"nav": "Custom review", "engine": "Mock (offline, free)",
                               "c_obj": "o", "c_claims": "alpha beta gamma\nzzz qqq www",
                               "c_ev": "alpha beta gamma delta"})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state["results_custom"]
    assert [a.claim.text for a in job["results"]] == ["alpha beta gamma", "zzz qqq www"]
    assert [a.claim.id for a in job["results"]] == ["c1", "c2"]


_VISA_URL = "https://www.gov.uk/standard-visitor-visa"
_VISA_PAGE_TEXT = ("Standard Visitor visa rules\n"
                   "You must hold a passport that stays valid for your whole visit.\n"
                   "You must show that you can support yourself during your visit.\n"
                   "If you visit family, you may need a letter of invitation.")


def _visa_session():
    return {"nav": "Visa review", "engine": "Mock (offline, free)",
            "v_text": "Alpha beta gamma\nZebra quasar wombat\nMango tango foxtrot",
            "v_src": "Demo list", "v_date": "2026-01-01",
            "v_ev": "Alpha beta gamma delta"}


def _fake_official_fetch(page_text, page_warning=""):
    from pruvfetch.fetch import FetchedDoc

    def _fetch(url, timeout=10):
        if url.endswith("/robots.txt"):
            return FetchedDoc(url=url, warning="HTTP 404")
        if page_warning:
            return FetchedDoc(url=url, warning=page_warning)
        return FetchedDoc(url=url, final_url=url, status=200, content_type="text/html",
                           text=page_text, size_bytes=len(page_text),
                           fetched_at="2026-10-29T00:00:00+00:00",
                           title="Standard Visitor visa rules (SYNTHETIC TEST PAGE)",
                           published="2026-01-15")

    return _fetch


def test_visa_run_renders_coverage_and_downloads(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_visa_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    job = fake.session_state["results_visa"]
    assert [a.claim.id for a in job["results"]] == ["v1", "v2", "v3"]
    assert any(c[0] == "subheader" and "Step 4. Review your results" in str(c[1])
               for c in fake.calls)
    assert any(c[0] == "caption" and "present for review" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "caption" and "Coverage: Ready for review" in str(c[1])
               for c in fake.calls)
    docs = _downloads(fake, "Download findings (.md)")
    assert docs
    for data, fname in docs:
        assert data.startswith("# PruvChat findings: Visa review")
        assert "Checklist source: Demo list (2026-01-01)" in data
        assert "1 Ready for review / 0 Needs attention / 2 Missing evidence (3 total)" in data
        assert "Safety: Readiness is not approval" in data
        assert fname and "_mock_report.md" in fname
    full = _downloads(fake, "Download full report (.md)")
    assert full and all("Safety: Readiness is not approval" in d[0] for d in full)


def test_visa_save_reopen_restores_inputs(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_visa_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_visa"] = "visa-keep"
    fake.script = {"save_visa": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    fresh = FakeSt()
    fresh.script = {"open_btn": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    assert fresh.session_state["v_text"].startswith("Alpha beta gamma")
    assert fresh.session_state["v_src"] == "Demo list"
    assert fresh.session_state["v_date"] == "2026-01-01"
    assert "results_visa" in fresh.session_state
    fresh.script = {}
    fresh.calls.clear()
    _run_app_script(fresh, tmp_path)
    assert any(c[0] == "info" and "Restored saved findings" in str(c[1]) for c in fresh.calls)
    assert any(c[0] == "subheader" and "Step 4. Review your results" in str(c[1])
               for c in fresh.calls)
    assert any(c[0] == "download_button" for c in fresh.calls)
    # Findings use text statuses, never alert badges; a clean restore shows no errors.
    assert fresh.errors_shown == []


def test_visa_official_fetch_adds_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr("pruvfetch.official.fetch_url", _fake_official_fetch(_VISA_PAGE_TEXT))
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "official_url_visa": _VISA_URL})
    fake.script = {"fetch_official_visa": True}
    _run_app_script(fake, tmp_path)
    (rec,) = fake.session_state["official_records_visa"]
    assert rec["publisher"] == "GOV.UK" and rec["published"] == "2026-01-15"
    cands = fake.session_state["official_candidates_visa"]
    assert len(cands) >= 3
    assert all(c["status"] == "Needs human review" for c in cands)
    assert any(c[0] == "link_button" and _VISA_URL in str(c[1]) for c in fake.calls)
    assert any(c[0] == "success" and "Fetched:" in str(c[1]) for c in fake.calls)
    fake.session_state["vcand_0"] = True
    fake.script = {"Use selected as checklist items": True}
    _run_app_script(fake, tmp_path)
    assert cands[0]["text"] in fake.session_state["v_text"]
    assert fake.errors_shown == []


def test_visa_refresh_reports_changed_and_keeps_checklist(tmp_path, monkeypatch):
    from pruvfetch.fetch import FetchedDoc
    from pruvfetch.official import build_source_record

    old_text = _VISA_PAGE_TEXT
    new_text = old_text.replace("support yourself during your visit",
                                "show bank statements that cover the last six months")
    seed = build_source_record(_VISA_URL, FetchedDoc(url=_VISA_URL, final_url=_VISA_URL,
                                                     status=200, text=old_text),
                               "UK Standard Visitor visa",
                               retrieved_at="2026-01-01T00:00:00+00:00")
    monkeypatch.setattr("pruvfetch.official.fetch_url", _fake_official_fetch(new_text))
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_text": "Item one text here",
                               "official_records_visa": [seed]})
    fake.script = {"refresh_official_0": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["refresh_notice_visa"]["state"] == "Changed"
    assert fake.session_state.get("rereview_visa") is True
    assert fake.session_state["v_text"] == "Item one text here"  # never overwritten
    assert fake.session_state["official_records_visa"][0]["prev_excerpt"]
    fake.script = {}
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "warning" and "kept as they were" in str(c[1]) for c in fake.calls)
    # FakeSt records expander contents, not the expander itself.
    assert any(c[0] == "write" and "Previous check" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "write" and "Latest check" in str(c[1]) for c in fake.calls)


def test_visa_refresh_unchanged_and_uncheckable(tmp_path, monkeypatch):
    from pruvfetch.fetch import FetchedDoc
    from pruvfetch.official import build_source_record

    seed = build_source_record(_VISA_URL, FetchedDoc(url=_VISA_URL, final_url=_VISA_URL,
                                                     status=200, text=_VISA_PAGE_TEXT),
                               retrieved_at="2026-01-01T00:00:00+00:00")
    monkeypatch.setattr("pruvfetch.official.fetch_url", _fake_official_fetch(_VISA_PAGE_TEXT))
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "official_records_visa": [seed]})
    fake.script = {"refresh_official_0": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["refresh_notice_visa"]["state"] == "Unchanged"
    assert fake.session_state.get("rereview_visa") is None
    assert "prev_excerpt" not in fake.session_state["official_records_visa"][0]
    monkeypatch.setattr("pruvfetch.official.fetch_url",
                        _fake_official_fetch(_VISA_PAGE_TEXT, page_warning="HTTP 403"))
    stuck = FakeSt()
    stuck.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                                "official_records_visa": [seed]})
    stuck.script = {"refresh_official_0": True}
    _run_app_script(stuck, tmp_path)  # no rerun: the error shows inline
    assert any("Could not check" in e for e in stuck.errors_shown)
    assert stuck.session_state["official_records_visa"][0]["retrieved_at"] == \
        "2026-01-01T00:00:00+00:00"


def test_save_trace_contains_no_document_content(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_visa_session())
    fake.session_state["v_text"] = "ZebraQuasarPrivateMarker line one"
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_visa"] = "trace-check"
    fake.script = {"save_visa": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    trace = (tmp_path / ".pruvchat_runs" / "save_trace.log").read_text(encoding="utf-8")
    assert "mode=visa" in trace and "ZebraQuasarPrivateMarker" not in trace


_DASHBOARD_TARGETS = {
    "go_req": ("Requirements", "Requirements"),
    "go_dis": ("Business disputes", "Business disputes"),
    "go_cus": ("Custom review", "Custom review"),
    "go_visa": ("Visa review", "Visa review"),
}


def test_overview_shows_all_mode_cards(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    labels = [c[1] for c in fake.calls if c[0] == "button"]
    for label in ("Explore Requirements", "Explore Business disputes",
                  "Explore Custom review", "Explore Visa review"):
        assert label in labels
    assert any(c[0] == "header" and "Your evidence workspace" in str(c[1])
               for c in fake.calls)
    assert any(c[0] == "write" and "Choose what you want to check." in str(c[1])
               for c in fake.calls)


@pytest.mark.parametrize("key", ["go_req", "go_dis", "go_cus", "go_visa"])
def test_overview_button_opens_its_mode(tmp_path, key):
    # Regression net for the Visa review click crash: each overview
    # button runs through the real handler and the real page registry, then
    # the follow-up render must land on the mode page itself.
    from pruvcore.navigation import apply_pending_nav

    page, header = _DASHBOARD_TARGETS[key]
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {key: True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["_pending_nav"] == page
    assert apply_pending_nav(fake.session_state) == page
    follow = FakeSt()
    follow.session_state.update({"nav": page, "engine": "Mock (offline, free)"})
    follow.script = {}
    _run_app_script(follow, tmp_path)
    assert any(c[0] == "header" and header in str(c[1]) for c in follow.calls)


def test_sidebar_nav_between_overview_and_modes(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Custom review", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "header" and "Custom review" in str(c[1]) for c in fake.calls)
    fake.session_state["nav"] = "Overview"  # sidebar radio selection
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    labels = [c[1] for c in fake.calls if c[0] == "button"]
    assert "Explore Visa review" in labels and "Explore Requirements" in labels


def test_saved_label_leads_with_workspace_name(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_visa_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_visa"] = "my-check"
    fake.script = {"save_visa": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    fresh = FakeSt()
    fresh.script = {}
    _run_app_script(fresh, tmp_path)
    (label,) = fresh.choices[("selectbox", "open_pick")]
    assert label.startswith("my-check (visa) · ")


def test_visa_coverage_uses_plain_language(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_visa_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = [str(c[1]) for c in fake.calls if c[0] == "write"]
    assert any("What looks ready: 1 of 3" in t for t in texts)
    assert any("What needs attention: 2" in t for t in texts)
    assert any("What to do next:" in t for t in texts)


def test_visa_route_notes_and_custom_name(tmp_path, monkeypatch):
    monkeypatch.setattr("pruvfetch.official.fetch_url", _fake_official_fetch(_VISA_PAGE_TEXT))
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom",
                               "v_purpose": "Talent or specialist",
                               "v_route": "UK Global Talent visa",
                               "official_url_visa": _VISA_URL})
    fake.script = {"fetch_official_visa": True}
    _run_app_script(fake, tmp_path)
    (rec,) = fake.session_state["official_records_visa"]
    assert rec["route"] == "UK Global Talent visa"
    assert any(c[0] == "caption" and "pathway" in str(c[1]) for c in fake.calls)
    named = FakeSt()
    named.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                                "v_country_select": "United Kingdom",
                                "v_purpose": "Visit",
                                "v_route": "Custom official URL",
                                "v_route_name": "Family visit",
                                "official_url_visa": _VISA_URL})
    named.script = {"fetch_official_visa": True}
    _run_app_script(named, tmp_path)
    assert named.session_state["official_records_visa"][0]["route"] == "Family visit"


def test_top_nav_lists_all_pages_with_active_marked(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Business disputes", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    nav = [(c[1], c[2], c[3]) for c in fake.calls
           if c[0] == "button" and str(c[2]).startswith("nav_")]
    assert [label for label, _, _ in nav] == ["Overview", "Requirements",
                                              "Custom", "Visa review"]
    assert {kind for _, _, kind in nav} == {"tertiary"}
    assert [key for _, key, _ in nav] == ["nav_0", "nav_1", "nav_3", "nav_4"]
    assert any(c[0] == "write" and "**Disputes**" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("key,page", [("nav_1", "Requirements"),
                                      ("nav_2", "Business disputes"),
                                      ("nav_3", "Custom review"),
                                      ("nav_4", "Visa review")])
def test_top_nav_button_navigates(tmp_path, key, page):
    from pruvcore.navigation import apply_pending_nav

    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {key: True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["_pending_nav"] == page
    assert apply_pending_nav(fake.session_state) == page


def test_visa_country_picker_sets_destination(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)"})
    fake.script = {"v_cty_Japan": True}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_country"] == "Japan"
    assert fake.session_state["v_country_select"] == "Japan"


def test_visa_purpose_change_remaps_route(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_purpose_applied"] == "Visit"
    fake.session_state["v_purpose"] = "Talent or specialist"
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "UK Global Talent visa"


def test_visa_unsupported_country_shows_general_category(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "France", "v_purpose": "Work"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_country"] == "France"
    assert fake.session_state["v_route"] == "Work (general category)"
    assert any(c[0] == "caption" and "not a confirmed" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "link_button" and "France-Visas" in str(c[1]) for c in fake.calls)
    fake.session_state["v_route"] = "Manual verification required"
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "warning" and "do not guess checklists" in str(c[1])
               for c in fake.calls)


def test_visa_global_talent_demo_loads_fixture(tmp_path):
    import shutil

    root_fix = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "fixtures")
    (tmp_path / "fixtures").mkdir()
    shutil.copy(os.path.join(root_fix, "visa_global_talent.json"),
                tmp_path / "fixtures" / "visa_global_talent.json")
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)"})
    fake.script = {"Try Global Talent demo": True}
    _run_app_script(fake, tmp_path)
    assert "endorsement letter" in fake.session_state["v_text"]
    assert fake.session_state["v_src"] == "Fictional Global Talent demo case"


def test_visa_progress_reflects_completed_steps(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "caption" and "Step 1 of 4" in str(c[1]) for c in fake.calls)
    fake.session_state.update({"v_country": "Japan", "v_route": "Manual verification required",
                               "v_text": "Item one text here"})
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "caption" and "Step 4 of 4" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("page", ["Overview", "Requirements", "Business disputes",
                                  "Custom review", "Visa review"])
def test_header_shows_brand_page_and_controls(tmp_path, page):
    fake = FakeSt()
    fake.session_state.update({"nav": page, "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "title" and "PruvChat" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "caption" and page in str(c[1]) for c in fake.calls)
    pops = {c[1]: c[2] for c in fake.calls if c[0] == "popover"}
    assert pops["Search"].get("icon") == ":material/search:"
    assert pops["Help"].get("icon") == ":material/help:"
    assert pops["Settings"].get("icon") == ":material/settings:"
    assert pops["Search"].get("type") == "tertiary"
    assert pops["Help"].get("type") == "tertiary"
    assert pops["Settings"].get("type") == "tertiary"
    assert ("text_input", "app_search") in [
        (c[0], c[2]) for c in fake.calls if c[0] == "text_input"]


def test_settings_panel_holds_engine_only(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert ("radio", "theme") not in fake.choices
    assert fake.choices[("radio", "engine")] == ["Mock (offline, free)",
                                                "Live Meta API (billed)"]
    assert not any(c[0] == "subheader" and "Appearance" in str(c[1]) for c in fake.calls)
    assert not any(c[0] == "subheader" and "Storage" in str(c[1]) for c in fake.calls)
    assert not any(c[0] == "subheader" and "Recent runs" in str(c[1]) for c in fake.calls)
    assert ("radio", "nav") not in fake.choices  # top menu replaced the radio
    assert any(c[0] == "caption" and "No saved runs yet" in str(c[1]) for c in fake.calls)


def test_page_config_auto_sidebar(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    cfgs = [c for c in fake.calls if c[0] == "set_page_config"]
    assert cfgs and cfgs[0][2].get("initial_sidebar_state") == "auto"


def test_overview_how_it_works_collapsed(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert not any(c[0] == "subheader" and "How a run works" in str(c[1])
                   for c in fake.calls)
    assert any("Add evidence" in str(c[1]) for c in fake.calls)


def test_help_matches_current_page(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "write" and "4 steps" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "write" and "word matching" in str(c[1]) for c in fake.calls)


def test_overview_card_titles_concise(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    titles = [c[1][0] for c in fake.calls if c[0] == "subheader"]
    cards = [t for t in titles
             if t in ("Requirements", "Business disputes", "Custom review", "Visa review")]
    assert cards == ["Requirements", "Business disputes", "Custom review", "Visa review"]


def test_search_finds_pages_and_saved_work(tmp_path):
    from pruvcore.store import save_run

    save_run(str(tmp_path), "trip-plan", "visa", {"requirements": "x"}, [], {"total": 0})
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)",
                               "app_search": "trip"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    labels = [c[1] for c in fake.calls if c[0] == "button"]
    assert "Open trip-plan" in labels
    fake.session_state["app_search"] = "visa"
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    labels = [c[1] for c in fake.calls if c[0] == "button"]
    assert "Go to Visa review" in labels
    assert "Open trip-plan" in labels  # saved mode name also matches
    fake.session_state["app_search"] = "qqq-nope"
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "caption" and "No matches" in str(c[1]) for c in fake.calls)


def test_search_go_to_navigates(tmp_path):
    from pruvcore.navigation import apply_pending_nav

    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)",
                               "app_search": "visa"})
    fake.script = {"sr_page_0": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["_pending_nav"] == "Visa review"
    assert apply_pending_nav(fake.session_state) == "Visa review"


def test_search_open_reuses_workspace_restore(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    fake.session_state["save_name_requirements"] = "trip-plan"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    fresh = FakeSt()
    fresh.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)",
                                "app_search": "trip"})
    fresh.script = {"sr_open_0": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fresh, tmp_path)
    assert fresh.session_state["req_text"] == "Alpha beta gamma."
    assert "results_requirements" in fresh.session_state


def test_button_hierarchy_tertiary_cards_primary_run(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    kinds = {c[2]: c[3] for c in fake.calls if c[0] == "button"}
    for key in ("go_req", "go_dis", "go_cus", "go_visa"):
        assert kinds[key] == "tertiary", key
    req = FakeSt()
    req.session_state.update({"nav": "Requirements", "engine": "Mock (offline, free)"})
    req.script = {}
    _run_app_script(req, tmp_path)
    run = [c for c in req.calls if c[0] == "button" and c[1] == "Run assessment"]
    assert run and run[0][3] == "primary"


def test_results_show_compact_summary_and_label_guide(tmp_path):
    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = " ".join(str(c[1]) for c in fake.calls if c[0] == "write")
    assert "1 finding: 1 Supported · 0 Needs review · 0 Missing." in texts
    assert "(contested)" in texts and "(unsupported)" in texts
    assert not any(c[0] == "metric" for c in fake.calls)


def test_finding_shows_simple_status_with_details_available(tmp_path):
    fake = FakeSt()
    fake.session_state.update({
        "nav": "Business disputes", "engine": "Mock (offline, free)",
        "d_claim": "Order 1042 arrived damaged and missing parts.",
        "d_a": "Order 1042 arrived with a cracked panel and missing screws.",
        "d_b": "Order 1042 passed warehouse inspection before shipping."})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = " ".join(str(c[1]) for c in fake.calls)
    assert "**Needs review**" in texts and "**Supported**" in texts
    assert "Next action:" in texts
    assert "Heuristic overlap:" in texts and "Method:" in texts
    assert "Contradiction flag" in texts  # material warning stays visible


def test_mock_note_labeled_as_separate_signal(tmp_path):
    fake = FakeSt()
    fake.session_state.update({
        "nav": "Business disputes", "engine": "Mock (offline, free)",
        "d_claim": "Order 1042 arrived damaged and missing parts.",
        "d_a": "Order 1042 arrived with a cracked panel and missing screws.",
        "d_b": "Order 1042 passed warehouse inspection before shipping."})
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    texts = " ".join(str(c[1]) for c in fake.calls)
    assert "CONTESTED:" in texts and "**Needs review**" in texts
    assert "Separate quick signal" in texts
    assert "not the finding above" in texts
    assert "Provider note (mock)" not in texts


def test_mock_banner_hidden_on_overview_shown_on_modes(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert not any(c[0] == "warning" and "MOCK MODE" in str(c[1]) for c in fake.calls)
    fake.session_state["nav"] = "Requirements"
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "warning" and "MOCK MODE" in str(c[1]) for c in fake.calls)


@pytest.mark.parametrize("country,purpose,first", [
    ("United States", "Work", "Work (general category)"),
    ("Canada", "Study", "Study (general category)"),
    ("Australia", "Visit", "Visit (general category)"),
    ("Germany", "Join family", "Join family (general category)"),
    ("France", "Talent or specialist", "Talent or specialist (general category)"),
    ("Japan", "Visit", "Visit (general category)"),
])
def test_named_destination_offers_general_category(tmp_path, country, purpose, first):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": country, "v_purpose": purpose})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_country"] == country
    assert fake.choices[("selectbox", "v_route")] == [
        first, "Not sure which route applies", "Manual verification required"]
    assert fake.session_state["v_route"] == first
    assert any(c[0] == "caption" and "not a confirmed" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "caption" and "Country alone does not set the route" in str(c[1])
               for c in fake.calls)


def test_uk_offers_verified_presets_plus_manual_paths(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom", "v_purpose": "Visit"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.choices[("selectbox", "v_route")] == [
        "UK Standard Visitor visa", "UK Global Talent visa", "UK Skilled Worker visa",
        "UK Student visa", "UK Family visa",
        "Not sure which route applies", "Custom official URL"]
    assert fake.session_state["v_route"] == "UK Standard Visitor visa"


def test_purpose_change_resets_stale_route(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United States", "v_purpose": "Work"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "Work (general category)"
    fake.session_state["v_purpose"] = "Study"  # user changes purpose
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "Study (general category)"
    assert fake.choices[("selectbox", "v_route")][0] == "Study (general category)"


def test_country_change_revalidates_route(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom", "v_purpose": "Visit"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "UK Standard Visitor visa"
    fake.session_state["v_country_select"] = "Japan"
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "Visit (general category)"


def test_unknown_route_resets_to_first_option(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom", "v_purpose": "Visit",
                               "v_route": "Bogus visa"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_route"] == "UK Standard Visitor visa"


def test_unsure_route_shows_guidance_and_portal(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United States", "v_purpose": "Visit",
                               "v_route": "Not sure which route applies"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "caption" and "Not sure is fine" in str(c[1]) for c in fake.calls)
    assert any(c[0] == "link_button" and "USCIS" in str(c[1]) for c in fake.calls)


def test_typed_other_destination_stays_manual_without_portal(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "Other country",
                               "v_country_other": "Brazil", "v_purpose": "Visit"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_country"] == "Brazil"
    assert fake.session_state["v_route"] == "Visit (general category)"
    assert any(c[0] == "caption" and "No verified portal link" in str(c[1])
               for c in fake.calls)


def test_undecided_destination_defaults_to_manual(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "Other country", "v_purpose": "Visit"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert fake.session_state["v_country"] == ""
    assert fake.session_state["v_route"] == "Manual verification required"
    assert any(c[0] == "caption" and "Pick a destination above first" in str(c[1])
               for c in fake.calls)


def test_key_controls_have_plain_language_tooltips(tmp_path):
    visa = FakeSt()
    visa.session_state.update({"nav": "Visa review", "engine": "Mock (offline, free)",
                               "v_country_select": "United Kingdom", "v_purpose": "Visit"})
    visa.script = {}
    _run_app_script(visa, tmp_path)
    assert "word matching" in visa.helps[("radio", "engine")]
    assert "resets the route" in visa.helps[("radio", "v_purpose")]
    assert "stay manual" in visa.helps[("selectbox", "v_route")]
    assert "checked against your evidence" in visa.helps[("text_area", "v_text")]
    assert "quote these exact lines" in visa.helps[("text_area", "v_ev")]
    assert "exact official page" in visa.helps[("text_input", "official_url_visa")]
    req = FakeSt()
    req.session_state.update(_fresh_session())
    req.script = {}
    _run_app_script(req, tmp_path)
    assert "current inputs" in req.helps[("button", "Run assessment")]
    assert "quote these exact lines" in req.helps[("text_area", "req_ev")]
    cus = FakeSt()
    cus.session_state.update({"nav": "Custom review", "engine": "Mock (offline, free)"})
    cus.script = {}
    _run_app_script(cus, tmp_path)
    assert "must answer" in cus.helps[("text_area", "c_obj")]
    assert "quote these exact lines" in cus.helps[("text_area", "c_ev")]


def test_guide_shows_by_default_and_skips(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "subheader" and "Understand your workspace" in str(c[1])
               for c in fake.calls)
    fake.script = {"guide_skip": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["hide_guide"] is True
    fake.script = {}
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert not any(c[0] == "subheader" and "Understand your workspace" in str(c[1])
                   for c in fake.calls)


def test_guide_close_and_reopen_from_help(tmp_path):
    fake = FakeSt()
    fake.session_state.update({"nav": "Overview", "engine": "Mock (offline, free)"})
    fake.script = {"guide_close": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["hide_guide"] is True
    fake.script = {"guide_show": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    assert fake.session_state["hide_guide"] is False
    fake.script = {}
    fake.calls.clear()
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "subheader" and "Understand your workspace" in str(c[1])
               for c in fake.calls)


def test_user_name_personalizes_greeting_and_stays_session_only(tmp_path):
    import json

    from pruvcore.store import list_runs, load_run

    fake = FakeSt()
    fake.session_state.update(_fresh_session())
    fake.session_state["user_name"] = "Ada"
    fake.script = {"Run assessment": True}
    _run_app_script(fake, tmp_path)
    assert any(c[0] == "caption" and "Hello, Ada." in str(c[1]) for c in fake.calls)
    fake.session_state["save_name_requirements"] = "named-ws"
    fake.script = {"save_requirements": True}
    with pytest.raises(FakeRerun):
        _run_app_script(fake, tmp_path)
    (run,) = list_runs(str(tmp_path))
    saved = json.dumps(load_run(str(tmp_path), run["file"]))
    assert "user_name" not in saved and "Ada" not in saved
    trace = (tmp_path / ".pruvchat_runs" / "save_trace.log").read_text(encoding="utf-8")
    assert "Ada" not in trace

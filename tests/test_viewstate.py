"""View-state persistence: results survive the Save-click rerun.

Regression coverage for the bug where results (and the Save button itself)
only rendered while the Run button was True, so saving never executed.
"""
from pruvcore.store import list_runs, load_run, save_run
from pruvcore.viewstate import (
    clear_save_status,
    clear_stored_results,
    get_save_status,
    set_save_status,
    stash_results,
    take_stored_results,
)

MOCK = "Mock (offline, free)"
LIVE = "Live Meta API (billed)"


def _job():
    return {"results": ["r1"], "evidence": ["e1"], "inputs": {"a": "b"}}


def test_stash_take_round_trip():
    session = {}
    stash_results(session, "requirements", ["r1"], ["e1"], {"a": "b"}, MOCK)
    job = take_stored_results(session, "requirements", MOCK)
    assert job == {"results": ["r1"], "evidence": ["e1"], "inputs": {"a": "b"},
                   "engine": MOCK, "live_label": None, "model": "",
                   "restored_label": None, "fallback": False}


def test_engine_mismatch_hides_results():
    session = {}
    stash_results(session, "custom", ["r1"], ["e1"], {}, MOCK)
    assert take_stored_results(session, "custom", LIVE) is None
    assert take_stored_results(session, "custom", MOCK) is not None


def test_missing_clear_and_overwrite():
    session = {}
    assert take_stored_results(session, "requirements", MOCK) is None
    clear_stored_results(session, "requirements")  # safe when absent
    stash_results(session, "custom", ["old"], ["e"], {}, MOCK)
    stash_results(session, "custom", ["new"], ["e"], {}, MOCK)
    assert take_stored_results(session, "custom", MOCK)["results"] == ["new"]
    clear_stored_results(session, "custom")
    assert take_stored_results(session, "custom", MOCK) is None


def test_save_click_rerun_sequence_then_sidebar_lists_run(tmp_path):
    # Run 1 (Run click): compute + stash.
    session = {}
    job = _job()
    stash_results(session, "requirements", job["results"], job["evidence"],
                  job["inputs"], MOCK)
    # Run 2 (Save click): Run button is False, but stashed results still render,
    # so the save handler executes and the sidebar (list_runs) shows the run.
    stored = take_stored_results(session, "requirements", MOCK)
    assert stored is not None
    save_run(str(tmp_path), "ws1", "requirements", stored["inputs"],
             [{"title": "t"}], {"total": 1})
    runs = list_runs(str(tmp_path))
    assert len(runs) == 1 and runs[0]["name"] == "ws1"
    assert load_run(str(tmp_path), runs[0]["file"])["inputs"] == {"a": "b"}


def test_live_results_carry_label_and_stay_engine_gated():
    session = {}
    stash_results(session, "disputes-a", ["r"], ["e"], {}, LIVE, live_label="m1 · 1 verdict(s)")
    job = take_stored_results(session, "disputes-a", LIVE)
    assert job["live_label"] == "m1 · 1 verdict(s)"
    assert take_stored_results(session, "disputes-a", MOCK) is None


def test_save_status_round_trip_and_clear():
    session = {}
    assert get_save_status(session, "custom") is None
    set_save_status(session, "custom", True, "x.json")
    status = get_save_status(session, "custom")
    assert status["ok"] is True and status["message"] == "x.json" and status["at"]
    set_save_status(session, "custom", False, "boom")
    assert get_save_status(session, "custom")["ok"] is False
    clear_save_status(session, "custom")
    assert get_save_status(session, "custom") is None


def test_fallback_results_render_under_either_engine():
    from pruvcore.viewstate import take_fallback_results

    session = {}
    stash_results(session, "custom", ["r1"], ["e1"], {}, MOCK, fallback=True)
    assert take_stored_results(session, "custom", LIVE) is None  # still engine-gated
    assert take_fallback_results(session, "custom") is not None
    assert take_fallback_results(session, "requirements") is None
    stash_results(session, "custom", ["r1"], ["e1"], {}, MOCK)  # default: not fallback
    assert take_fallback_results(session, "custom") is None


def test_app_renders_stored_results_for_every_mode():
    import os
    app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    with open(app_path, encoding="utf-8") as fh:
        src = fh.read()
    for mode in ("requirements", "disputes-a", "disputes-b", "custom", "visa"):
        assert f'_render_stored_results("{mode}")' in src, mode

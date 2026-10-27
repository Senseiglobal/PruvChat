"""Local persistence: round trips, privacy scrub, corrupt-file tolerance."""
import json

import pytest

from pruvcore.store import delete_run, export_report, list_runs, load_run, sanitize_name, save_run


def _payload():
    return ("demo", "requirements", {"req_text": "r1"},
            [{"title": "SUPPORTED: x", "claim": "x", "status": "supported", "score": 1.0,
              "method": "m", "rationale": "r", "citations": [{"id": "e1", "locator": "L", "excerpt": "E"}],
              "contradicted_by": [], "uncertainty": "Low", "next_action": "n"}],
            {"supported": 1, "contested": 0, "unsupported": 0, "total": 1})


def test_save_list_load_round_trip(tmp_path):
    name, mode, inputs, cards, summary = _payload()
    path = save_run(str(tmp_path), name, mode, inputs, cards, summary)
    runs = list_runs(str(tmp_path))
    assert len(runs) == 1 and runs[0]["mode"] == "requirements"
    loaded = load_run(str(tmp_path), runs[0]["file"])
    assert loaded["cards"] == cards and loaded["summary"] == summary
    assert path.endswith(".json")


def test_name_sanitized_and_missing_guarded(tmp_path):
    assert sanitize_name("../../etc/pass") == "etc-pass"
    assert sanitize_name("  ") == "run"
    with pytest.raises(FileNotFoundError):
        load_run(str(tmp_path), "nope.json")
    with pytest.raises(ValueError):
        load_run(str(tmp_path), "../evil.json")
    assert delete_run(str(tmp_path), "nope.json") is False


def test_secrets_scrubbed_and_corrupt_skipped(tmp_path):
    name, mode, _, cards, summary = _payload()
    save_run(str(tmp_path), name, mode, {"api_key": "sk-live", "note": "ok"}, cards, summary)
    runs = list_runs(str(tmp_path))
    loaded = load_run(str(tmp_path), runs[0]["file"])
    assert loaded["inputs"] == {"api_key": "[redacted]", "note": "ok"}
    bad = tmp_path / ".pruvchat_runs" / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    assert len(list_runs(str(tmp_path))) == 1  # corrupt file skipped
    assert delete_run(str(tmp_path), runs[0]["file"]) is True
    assert list_runs(str(tmp_path)) == []


def test_export_report_sections(tmp_path):
    name, mode, inputs, cards, summary = _payload()
    save_run(str(tmp_path), name, mode, inputs, cards, summary)
    data = load_run(str(tmp_path), list_runs(str(tmp_path))[0]["file"])
    md = export_report(data)
    assert "# PruvChat report" in md and "Summary: 1 supported" in md
    assert "## SUPPORTED: x" in md and "[L]" in md
    assert json.loads(json.dumps(data))  # still JSON-safe

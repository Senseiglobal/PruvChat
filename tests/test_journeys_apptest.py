"""Real-script user journeys via Streamlit AppTest. No saves, no network.

AppTest executes the actual app.py top to bottom with real widget state,
so these journeys catch wiring bugs the scripted FakeSt harness cannot
see (widget key collisions, execution-order faults, rendering crashes).
They never click Save/Delete/Fetch, so they write nothing and fetch
nothing: Mock mode, offline fixtures only.
"""
import os
import socket

import pytest

try:
    _probe = socket.socketpair()
except OSError:
    pytest.skip("AppTest needs loopback sockets, blocked in this sandbox",
                allow_module_level=True)
else:
    for _sock in _probe:
        _sock.close()

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
MOCK = "Mock (offline, free)"


def _run(path=APP):
    at = AppTest(path, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _button(at, label=None, key=None):
    for btn in at.button:
        if label is not None and btn.label != label:
            continue
        if key is not None and btn.key != key:
            continue
        return btn
    raise AssertionError(f"button not found: label={label!r} key={key!r}")


def _click(at, label=None, key=None):
    _button(at, label=label, key=key).click()
    at.run()
    assert not at.exception, at.exception


def _texts(at):
    """All visible text across common elements."""
    out = []
    for seq in (at.header, at.subheader, at.caption, at.markdown,
                at.warning, at.error, at.info, at.success):
        out.extend(el.value for el in seq)
    return " ".join(str(v) for v in out)


def test_journey_overviewLoads_with_guide_and_nav():
    at = _run()
    assert at.title[0].value == "PruvChat"
    assert "Understand your workspace" in _texts(at)
    labels = {btn.label for btn in at.button if (btn.key or "").startswith("nav_")}
    assert labels == {"Requirements", "Disputes", "Custom", "Visa review"}
    _click(at, key="guide_skip")
    assert "Understand your workspace" not in _texts(at)


def test_journey_top_nav_reaches_every_page():
    at = _run()
    assert at.header[0].value == "Your evidence workspace"
    for key, header in (("nav_1", "Requirements"), ("nav_2", "Business disputes"),
                        ("nav_3", "Custom review"), ("nav_4", "Visa review")):
        _click(at, key=key)
        assert at.header[0].value == header, key
    _click(at, key="nav_0")
    assert at.header[0].value == "Your evidence workspace"


def test_journey_requirements_assess():
    at = _run()
    _click(at, key="nav_1")
    _click(at, label="Try example")
    _click(at, label="Run assessment")
    texts = _texts(at)
    assert "findings:" in texts and "Supported" in texts
    assert "What these labels mean" in " ".join(e.label for e in at.expander)


def test_journey_disputes_assess_both_sides():
    at = _run()
    _click(at, key="nav_2")
    _click(at, label="Try example")
    _click(at, label="Run assessment")
    texts = _texts(at)
    assert "Against Side A" in texts and "Against Side B" in texts
    assert texts.count("finding:") >= 2  # one summary per side


def test_journey_custom_one_claim_per_line():
    at = _run()
    _click(at, key="nav_3")
    at.text_area(key="c_claims").set_value("Zebra quasar wombat.\nMango tango foxtrot.")
    at.text_area(key="c_ev").set_value("Zebra quasar wombat.")
    at.run()
    assert not at.exception, at.exception
    _click(at, label="Run assessment")
    assert "2 findings: 1 Supported" in _texts(at)


def test_journey_visa_route_flow_and_coverage():
    at = _run()
    _click(at, key="nav_4")
    _click(at, key="v_cty_USA")
    at.radio(key="v_purpose").set_value("Work")
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="v_route").value == "Work (general category)"
    assert "not a confirmed" in _texts(at)
    at.text_area(key="v_text").set_value("Item one text here\nZebra quasar wombat")
    at.text_area(key="v_ev").set_value("Item one text here")
    at.run()
    assert not at.exception, at.exception
    _click(at, label="Run assessment")
    texts = _texts(at)
    assert "What looks ready: 1 of 2" in texts
    assert "Coverage:" in texts


def test_journey_engine_defaults_to_mock_with_banner():
    at = _run()
    assert at.radio(key="engine").value == MOCK
    assert "MOCK MODE" not in _texts(at)  # calm overview
    _click(at, key="nav_1")
    assert "MOCK MODE" in _texts(at)


def test_journey_search_box_filters_without_crash():
    at = _run()
    at.text_input(key="app_search").set_value("visa")
    at.run()
    assert not at.exception, at.exception
    assert any(btn.label == "Go to Visa review" for btn in at.button)

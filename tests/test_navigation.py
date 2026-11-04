"""Navigation logic plus a source guard against post-instantiation writes."""
import os
import re

import pytest

from pruvcore.navigation import PAGES, apply_pending_nav, request_nav

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def test_pages_cover_all_five_modes():
    assert PAGES == ("Overview", "Requirements", "Business disputes", "Custom review",
                     "Visa review")


def test_request_then_apply_round_trip():
    session = {"nav": "Overview"}
    request_nav(session, "Custom review")
    assert session == {"nav": "Overview", "_pending_nav": "Custom review"}
    assert apply_pending_nav(session) == "Custom review"
    assert session == {"nav": "Custom review"}


@pytest.mark.parametrize("page", PAGES)
def test_every_page_navigates(page):
    session = {}
    request_nav(session, page)
    assert apply_pending_nav(session) == page


def test_invalid_pending_dropped_and_default_applied():
    assert apply_pending_nav({"_pending_nav": "Nope"}) == "Overview"
    assert apply_pending_nav({}) == "Overview"
    assert apply_pending_nav({"nav": "Custom review"}) == "Custom review"
    with pytest.raises(ValueError):
        request_nav({}, "Nope")


def test_two_run_button_sequence_never_touches_nav_directly():
    # Run 1: overview card click stages pending; nav key untouched.
    run1 = {"nav": "Overview"}
    request_nav(run1, "Requirements")
    assert run1["nav"] == "Overview"
    # Run 2 (after rerun): pending applied BEFORE the radio widget reads nav.
    assert apply_pending_nav(run1) == "Requirements"
    assert "_pending_nav" not in run1


def test_app_has_no_direct_nav_writes():
    with open(_APP, encoding="utf-8") as fh:
        src = fh.read()
    writes = re.findall(r"session_state\[.nav.\]\s*=", src)
    assert writes == [], f"direct nav writes would crash Streamlit: {writes}"
    # No nav widget: the top menu and cards navigate via request_nav, and
    # apply_pending_nav runs at the top of every run.
    assert 'key="nav"' not in src
    assert "_NAV_ITEMS" in src
    for label, page in (("Overview", "Overview"), ("Requirements", "Requirements"),
                        ("Disputes", "Business disputes"), ("Custom", "Custom review"),
                        ("Visa review", "Visa review")):
        assert f'("{label}", "{page}")' in src, label
        assert page in PAGES, page
    # Overview cards come from one map filtered against the registry, so a
    # card can never request an unregistered page.
    assert "_DASHBOARD_CARDS" in src
    assert 'if c["page"] in PAGES' in src
    assert 'request_nav(st.session_state, card["page"])' in src
    for page in ("Requirements", "Business disputes", "Custom review", "Visa review"):
        assert f'"page": "{page}"' in src, page
        assert page in PAGES, page
    assert "request_nav(st.session_state, _nav_page)" in src
    assert "_back_to_overview" not in src
    assert "apply_pending_nav(st.session_state)" in src

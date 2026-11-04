"""Streamlit-safe page navigation. Pure functions over a session dict.

Streamlit raises if a widget's session key is written after the widget is
instantiated in the same run. Buttons therefore stage navigation in a
_pending_ key; apply_pending_nav() runs at the top of every run, before
the page branches read the current page.
No streamlit import here, so this module is unit-testable offline.
"""
from __future__ import annotations

PAGES = ("Overview", "Requirements", "Business disputes", "Custom review", "Visa review")
NAV_KEY = "nav"
PENDING_KEY = "_pending_nav"


def request_nav(session: dict, page: str) -> None:
    """Stage a page change from a button handler. Raises on unknown pages."""
    if page not in PAGES:
        raise ValueError(f"unknown page: {page!r}")
    session[PENDING_KEY] = page


def apply_pending_nav(session: dict) -> str:
    """Apply staged navigation; call at the top of the run.

    Drops invalid pending values, defaults missing nav to the Overview,
    and returns the current page.
    """
    pending = session.pop(PENDING_KEY, None)
    if pending in PAGES:
        session[NAV_KEY] = pending
    current = session.get(NAV_KEY)
    if current not in PAGES:
        current = session[NAV_KEY] = PAGES[0]
    return current

"""UI view-state: persist rendered results across Streamlit reruns.

A Streamlit button is True for exactly one rerun, so results computed inside
a Run-button handler vanish on the next interaction (e.g. clicking Save).
They take the Save button itself with them. Stash results in session state at
compute time and render from the stash on every rerun instead.

Retrieval is engine-gated so mock results never render under the live banner
or vice versa. Pure functions over a session dict; no streamlit import.
"""
from __future__ import annotations

import datetime as _dt

RESULTS_PREFIX = "results_"
SAVE_STATUS_PREFIX = "save_status_"


def _key(mode: str) -> str:
    return f"{RESULTS_PREFIX}{mode}"


def _status_key(mode: str) -> str:
    return f"{SAVE_STATUS_PREFIX}{mode}"


def stash_results(session: dict, mode: str, results: list, evidence: list,
                  inputs: dict, engine: str, live_label: str | None = None,
                  model: str = "", restored_label: str | None = None,
                  fallback: bool = False) -> None:
    """Store a computed run for re-rendering on later reruns (overwrites)."""
    session[_key(mode)] = {"results": results, "evidence": evidence, "inputs": inputs,
                           "engine": engine, "live_label": live_label,
                           "model": model, "restored_label": restored_label,
                           "fallback": bool(fallback)}


def take_stored_results(session: dict, mode: str, engine: str) -> dict | None:
    """Return the stashed job only when its engine matches the current one."""
    job = session.get(_key(mode))
    if not isinstance(job, dict) or job.get("engine") != engine:
        return None
    return job


def take_restored_results(session: dict, mode: str) -> dict | None:
    """Return the stashed job only when it came from a saved file.

    Restored findings carry explicit provenance labels, so they may render
    under either engine without masquerading as fresh output.
    """
    job = session.get(_key(mode))
    if not isinstance(job, dict) or not job.get("restored_label"):
        return None
    return job


def take_fallback_results(session: dict, mode: str) -> dict | None:
    """Return the stashed job only when it is an explicit fallback.

    Fallback placeholders are labeled UNVERIFIED on every card, so they may
    render under either engine without masquerading as verdicts.
    """
    job = session.get(_key(mode))
    if not isinstance(job, dict) or not job.get("fallback"):
        return None
    return job


def clear_stored_results(session: dict, mode: str) -> None:
    """Drop stashed results (e.g. when inputs are replaced by a fixture)."""
    session.pop(_key(mode), None)


def set_save_status(session: dict, mode: str, ok: bool, message: str) -> None:
    """Record the last save outcome so the UI can show it on every rerun."""
    session[_status_key(mode)] = {"ok": bool(ok), "message": str(message),
                                  "at": _dt.datetime.now().strftime("%H:%M:%S")}


def get_save_status(session: dict, mode: str) -> dict | None:
    """Return the last save outcome for this mode, if any."""
    status = session.get(_status_key(mode))
    return status if isinstance(status, dict) else None


def clear_save_status(session: dict, mode: str) -> None:
    """Drop a stale save outcome (e.g. when a new run starts)."""
    session.pop(_status_key(mode), None)

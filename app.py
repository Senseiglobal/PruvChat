"""PruvChat evidence intelligence workspace. Mock assessment core.

Verdicts are deterministic keyword-overlap heuristics, never AI judgments.
URL retrieval fetches public documents only (SSRF-guarded); saved runs stay
on this machine under .pruvchat_runs/.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
from urllib.parse import urlsplit

import streamlit as st

from providers import KNOWN_MODELS, get_provider
from providers.meta_live import ConfigError, MetaConfig, ProviderError
from providers.meta_mock import MockMetaProvider
from pruvcards.render import assessment_to_card, assessments_to_markdown, plain_verdict, summarize, to_blockquote
from pruvcore.countries import COUNTRIES, QUICK_COUNTRIES
from pruvcore.navigation import PAGES, apply_pending_nav, request_nav
from pruvcore.pipeline import (annotate_contradictions, assess,
                               fallback_unverified, uncertainty_for)
from pruvcore.schemas import Assessment, Claim, EvidenceRef, Verdict
from pruvcore.viewstate import (
    clear_save_status,
    clear_stored_results,
    get_save_status,
    set_save_status,
    stash_results,
    take_fallback_results,
    take_restored_results,
    take_stored_results,
)
from pruvcore.visa import (COVERAGE_HELP, SAFETY_NOTE, coverage_for,
                           coverage_line, coverage_summary)
from pruvcore.store import (
    delete_run,
    export_report,
    list_runs,
    load_run,
    restore_workspace,
    save_run,
)
from pruvfetch.fetch import FetchedDoc, fetch_url
from pruvfetch.official import (COUNTRY_PORTALS, PRESET_ROUTES, extract_candidates,
                                pack_sources, refresh_state, request_source,
                                unpack_sources)
from pruvfetch.uploads import read_uploads
from pruvfetch.urls import validate_url
from ui.theme import css_for

_MOCK = "Mock (offline, free)"
_LIVE = "Live Meta API (billed)"

_PROJDIR = _os.path.dirname(_os.path.abspath(__file__))
_FIXDIR = _os.path.join(_PROJDIR, "fixtures")
_provider = MockMetaProvider()

_PAGE_HELP = {
    "Overview": ("Pick a workspace below to begin.",
                 "Saved work lives in the sidebar."),
    "Requirements": ("Paste requirements, add evidence, then run.",
                     "Each card shows its sources."),
    "Business disputes": ("Paste each side, then run.",
                          "Flags highlight disagreement for review."),
    "Custom review": ("Write claims and evidence, then run.",
                      "Add a public link when you need one."),
    "Visa review": ("Follow the 4 steps on this page.",
                    "Confirm official addresses before fetching."),
}
_PAGE_HELP_EXTRA = ("Evidence can be pasted text, uploaded files, or a fetched public page.",
                    "Cards cite exact sources. Mock uses word matching; Live uses the paid Meta API.")
_NAV_ITEMS = (("Overview", "Overview"), ("Requirements", "Requirements"),
              ("Disputes", "Business disputes"), ("Custom", "Custom review"),
              ("Visa review", "Visa review"))


def _settings_panel() -> None:
    """Name and AI engine. Session-only personal settings."""
    st.text_input("Your name (optional)", key="user_name",
                  placeholder="What should we call you?",
                  help="Session only. Used for a friendly greeting, nothing else.")
    st.caption("Your name stays in this session. It is never saved or sent anywhere.")
    st.radio("AI engine", [_MOCK, _LIVE], key="engine",
             help="Mock uses word matching and is free. Live calls the paid Meta API.")
    if st.session_state.get("engine") == _LIVE:
        st.selectbox("Model", list(KNOWN_MODELS), key="live_model")
        try:
            _cfg = MetaConfig.local(_PROJDIR)
            _host = urlsplit(_cfg.base_url).hostname or _cfg.base_url
            st.success(f"Key: configured · {_host} (key never shown)")
        except ConfigError:
            st.error("Key: missing. Live calls stay off until you add one.")
            with st.expander("How to add a key"):
                st.write("1) Copy `.env.example` to `.env` in the project folder.\n"
                         "2) Set `MODEL_API_KEY` to your Meta Model API key.\n"
                         "3) Restart Streamlit. `.env` stays out of git and is never displayed.")
        _spend = st.session_state.get("live_spend", {"calls": 0, "usd": 0.0})
        st.caption(f"Session live spend: {_spend['calls']} call(s), ≈${_spend['usd']:.4f} (rough estimate)")


def _search_results() -> None:
    """Filter saved workspaces and pages by the search box. Runs every rerun."""
    query = (st.session_state.get("app_search") or "").strip().lower()
    if not query:
        st.caption("Searches saved workspaces and pages.")
        return
    pages = [p for p in PAGES if query in p.lower()]
    runs = [r for r in list_runs(_PROJDIR)
            if query in r["name"].lower() or query in r["mode"].lower()]
    if not pages and not runs:
        st.caption("No matches. Try a workspace name.")
        return
    for pos, page in enumerate(pages):
        if st.button(f"Go to {page}", key=f"sr_page_{pos}"):
            request_nav(st.session_state, page)
            st.rerun()
    for pos, run in enumerate(runs):
        if st.button(f"Open {run['name']}", key=f"sr_open_{pos}"):
            # Staged like _pending_nav: _open_workspace is defined below the
            # header, so the processor after its def runs the open this run.
            st.session_state["_search_open"] = run["file"]


st.set_page_config(page_title="PruvChat", layout="wide", initial_sidebar_state="auto")
st.markdown(css_for(), unsafe_allow_html=True)
apply_pending_nav(st.session_state)
_current_page = st.session_state.get("nav", "Overview")
_engine_short = "Live" if st.session_state.get("engine", _MOCK) == _LIVE else "Mock"
_brand, _search_col, _help_col, _gear_col = st.columns([4, 1, 1, 1])
with _brand:
    st.title("PruvChat")
    _greet = (st.session_state.get("user_name") or "").strip()
    st.caption(f"{_current_page} · {_engine_short} engine."
               + (f" Hello, {_greet}." if _greet else ""))
with _search_col:
    with st.popover("Search", icon=":material/search:", type="tertiary"):
        st.text_input("Search saved work and pages", key="app_search",
                      placeholder="Type a name…", label_visibility="collapsed")
        _search_results()
with _help_col:
    with st.popover("Help", icon=":material/help:", type="tertiary"):
        for _line in _PAGE_HELP.get(_current_page, _PAGE_HELP["Overview"]):
            st.write(_line)
        for _line in _PAGE_HELP_EXTRA:
            st.write(_line)
        if st.session_state.get("hide_guide") and st.button("Show workspace guide",
                                                            key="guide_show",
                                                            type="tertiary"):
            st.session_state["hide_guide"] = False
            st.rerun()
with _gear_col:
    with st.popover("Settings", icon=":material/settings:", type="tertiary"):
        _settings_panel()
_nav_cols = st.columns(5)
for _pos, (_nav_col, (_nav_label, _nav_page)) in enumerate(zip(_nav_cols, _NAV_ITEMS)):
    with _nav_col:
        if _nav_page == _current_page:
            st.write(f"**{_nav_label}**")
        elif st.button(_nav_label, key=f"nav_{_pos}", type="tertiary"):
            request_nav(st.session_state, _nav_page)
            st.rerun()
if _current_page != "Overview":
    if st.session_state.get("engine", _MOCK) == _LIVE:
        st.error(
            "LIVE MODE. Each assessment calls the Meta Model API and may spend credits. "
            "Every run needs you to confirm first. Saved runs stay on this machine."
        )
    else:
        st.warning(
            "MOCK MODE. Verdicts use simple word matching, not AI judgment. "
            "Nothing leaves this machine except pages you choose to fetch."
        )


def _load_fixture(name: str) -> dict:
    with open(_os.path.join(_FIXDIR, name), encoding="utf-8") as fh:
        return _json.load(fh)


def _evin(text: str, prefix: str, source: str = "pasted", locator: str = "pasted text") -> list:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return [EvidenceRef(id=f"{prefix}{i + 1}", text=ln, source=source,
                        locator=f"{locator} #{i + 1}") for i, ln in enumerate(lines)]


def _record_run(mode: str, summary: dict) -> None:
    runs = st.session_state.setdefault("runs", [])
    runs.append({"time": _dt.datetime.now().strftime("%H:%M:%S"), "mode": mode, **summary})
    st.session_state["runs"] = runs[-10:]


def _assess_staged(claims: list, evidence: list, context: list | None = None) -> list:
    """Run the pipeline with visible stage progress; annotate contradictions."""
    with st.status("Assessing evidence…", expanded=False) as status:
        st.write(f"Step 1 of 3. Found {len(claims)} claim(s).")
        results = assess(claims, evidence)
        st.write(f"Step 2 of 3. Scored {len(evidence)} evidence item(s).")
        annotated = annotate_contradictions(results, list(context) if context else evidence)
        flagged = sum(1 for r in annotated if r.contradicted_by)
        st.write(f"Step 3 of 3. Flagged {flagged} claim(s) for review.")
        status.update(label="Assessment complete", state="complete")
    return annotated


def _fetch_panel(key: str) -> list:
    """Opt-in public-URL retrieval; returns fetched evidence (may be empty).

    The fetched document is stashed in session state at fetch time: the
    Fetch button is True for exactly one rerun, so without the stash the
    text would vanish before the user clicks Run assessment. Network I/O
    happens only inside the explicit Fetch click. Never on other reruns.
    """
    st.subheader("Add a public document by URL")
    st.caption("Public links only. This blocks localhost, private networks, and login pages.")
    url = st.text_input("Document URL", key=f"url_{key}", placeholder="https://example.com/spec")
    use = st.checkbox("Use fetched text as evidence", value=True, key=f"use_{key}")
    stash_key = f"fetched_{key}"
    if st.button("Fetch public document", key=f"fetch_{key}"):
        if not url:
            st.error("Enter a URL first.")
            return []
        with st.spinner("Fetching with safety checks…"):
            doc = fetch_url(url)
        if doc.warning and not doc.text:
            st.error(f"Fetch blocked or failed: {doc.warning}")
            st.session_state.pop(stash_key, None)
            return []
        st.session_state[stash_key] = {"url": url, "doc": doc}
    stashed = st.session_state.get(stash_key)
    doc = stashed.get("doc") if isinstance(stashed, dict) else None
    if not isinstance(doc, FetchedDoc) or stashed.get("url") != url:
        if isinstance(stashed, dict) and stashed.get("url") and stashed.get("url") != url:
            st.caption("The URL changed since the last fetch. Please click Fetch again to attach it.")
        return []
    st.success(f"Fetched {doc.size_bytes} bytes. File type: {doc.content_type or 'unknown type'}")
    st.caption(f"Source: {doc.final_url} · HTTP {doc.status} · retrieved {doc.fetched_at}"
               + (f" · WARNING: {doc.warning}" if doc.warning else "")
               + (" · truncated at cap" if doc.truncated else ""))
    if not use:
        st.caption("Fetched text is held but excluded from the assessment (checkbox off).")
        return []
    paras = [p.strip() for p in doc.text.splitlines() if p.strip()][:40]
    refs = [EvidenceRef(id=f"w{i + 1}", text=p, source="url", locator=f"url:{doc.final_url}")
            for i, p in enumerate(paras)]
    if not refs:
        st.caption("Fetched document has no text lines to attach as evidence.")
        return []
    st.caption(f"{len(refs)} fetched item(s) attached as evidence (w1 to w{len(refs)}).")
    return refs


def _visa_country_picker() -> None:
    """Quick destination buttons plus the full searchable list.

    Buttons write both the selectbox key and the plain v_country key before
    the selectbox exists; afterwards the selectbox stays the source of truth.
    "Other country" means undecided and needs an explicit pick.
    """
    quick = list(QUICK_COUNTRIES)
    for row in (quick[:4], quick[4:]):
        cols = st.columns(4)
        for col, (short, full) in zip(cols, row):
            with col:
                if st.button(short, key=f"v_cty_{short}"):
                    st.session_state["v_country_select"] = full
                    st.session_state["v_country"] = "" if full == "Other country" else full
    rest = [c for c in COUNTRIES
            if c not in {full for _, full in quick if full != "Other country"}]
    options = ["Other country"] + [full for _, full in quick
                                   if full != "Other country"] + rest
    st.selectbox("Or pick any destination", options, key="v_country_select",
                 help="Type to search the full country list.")
    picked = st.session_state.get("v_country_select", "")
    if picked == "Other country":
        st.text_input("Destination name", key="v_country_other",
                      placeholder="Type the destination",
                      help="Labels this review only. Routes stay manual until you verify them.")
        st.session_state["v_country"] = (st.session_state.get("v_country_other") or "").strip()
        if not st.session_state["v_country"]:
            st.caption("Pick your destination from the full list above, or type its name.")
    else:
        st.session_state["v_country"] = picked


def _render_official_sources() -> None:
    """Show stashed official records, refresh actions, and candidate checkboxes.

    Records render from session state on every rerun. Refresh re-fetches one
    source and compares content hashes; checklist items are never overwritten.
    """
    notice = st.session_state.get("refresh_notice_visa")
    if notice:
        if notice.get("state") == "Changed":
            st.warning(f"Changed since the last check ({notice.get('at')}). "
                       "Requirements were kept as they were. Compare below, then run again.")
        else:
            st.success(f"Unchanged since the last check ({notice.get('at')}).")
    records = st.session_state.get("official_records_visa", [])
    for pos, rec in enumerate(records):
        with st.container(border=True):
            st.subheader(rec.get("title") or "Official source")
            st.caption(f"{rec.get('publisher') or 'Official source'} · "
                       f"retrieved {rec.get('retrieved_at') or '?'} (UTC)")
            st.caption(f"Published or updated: {rec.get('published') or 'not available'}")
            if rec.get("note"):
                st.caption(f"Note: {rec['note']}")
            st.link_button("Open official source", rec.get("final_url") or rec.get("url"))
            if rec.get("prev_excerpt"):
                with st.expander("What changed since the last check"):
                    st.write(f"Previous check ({rec.get('prev_retrieved_at') or '?'}):")
                    st.markdown(to_blockquote(rec.get("prev_excerpt", "")))
                    st.write("Latest check:")
                    st.markdown(to_blockquote(rec.get("excerpt", "")))
            if st.button("Refresh official source", key=f"refresh_official_{pos}",
                           help="Fetch this page again and compare it with the last check."):
                with st.spinner("Rechecking this source…"):
                    fresh = request_source(rec.get("url"), rec.get("route"),
                                           st.session_state.setdefault("official_fetch_times", {}))
                if fresh["status"] == "error":
                    st.error(f"Could not check: {fresh['reason']}")
                else:
                    state = refresh_state(rec.get("text_hash"), fresh.get("text_hash"))
                    if state == "Changed":
                        fresh["prev_excerpt"] = rec.get("excerpt", "")
                        fresh["prev_retrieved_at"] = rec.get("retrieved_at", "")
                        st.session_state["rereview_visa"] = True
                    records[pos] = fresh
                    st.session_state["official_records_visa"] = records
                    st.session_state["official_candidates_visa"] = extract_candidates(
                        fresh.get("full_text", ""), fresh["id"],
                        fresh.get("final_url") or fresh.get("url"))
                    for cand_key in [k for k in st.session_state if k.startswith("vcand_")]:
                        st.session_state.pop(cand_key, None)
                    st.session_state["refresh_notice_visa"] = {
                        "state": state, "at": fresh.get("retrieved_at")}
                    st.rerun()
    cands = st.session_state.get("official_candidates_visa", [])
    if cands:
        st.subheader("Candidate requirements from official sources")
        st.caption("Each line is copied word for word from the fetched page. Tick the ones that "
                   "apply, then add them to the checklist. Every candidate needs human review. "
                   "Type labels come from wording cues only.")
        for i, cand in enumerate(cands):
            st.checkbox(cand["text"][:160], key=f"vcand_{i}")
            st.caption(f"Source: {cand['source_url']} · {cand['status']} · {cand['classification']}")
        if st.button("Use selected as checklist items"):
            picked = [c["text"] for i, c in enumerate(cands)
                      if st.session_state.get(f"vcand_{i}")]
            if not picked:
                st.error("Tick at least one candidate first.")
            else:
                current = [ln.strip() for ln in st.session_state.get("v_text", "").splitlines()
                           if ln.strip()]
                for item in picked:
                    if item not in current:
                        current.append(item)
                st.session_state["v_text"] = "\n".join(current)
                st.success(f"Added {len(picked)} item(s) to the checklist.")


def _dispatch_assessment(mode_key: str, claims: list, evidence: list, inputs: dict,
                         context: list | None = None) -> None:
    """Mock computes once and stashes; live stages a pending job for confirm.

    A live run with missing claims or evidence can produce no verdict: it gets
    deterministic UNVERIFIED placeholders stashed under the MOCK engine, so a
    fallback is never labeled, saved, or restored as a live judgment.
    """
    engine = st.session_state.get("engine", _MOCK)
    clear_save_status(st.session_state, mode_key)
    st.session_state.pop(f"restore_notice_{mode_key}", None)
    if engine != _LIVE:
        results = _assess_staged(claims, evidence, context)
        _record_run(mode_key, summarize(results))
        stash_results(st.session_state, mode_key, results, evidence, inputs, engine)
        return
    if not claims or not evidence:
        missing = "claims" if not claims else "evidence"
        st.warning(f"Live assessment needs both claims and evidence (missing: {missing}). "
                   "Nothing was billed. Findings below are UNVERIFIED placeholders. They are not live verdicts.")
        results = fallback_unverified(
            claims, f"no {missing} supplied for live assessment.",
            method="live fallback: unverified (inputs incomplete; nothing billed)")
        _record_run(mode_key, summarize(results))
        stash_results(st.session_state, mode_key, results, evidence, inputs, _MOCK, fallback=True)
        return
    pending = st.session_state.setdefault("live_pending", {})
    clear_stored_results(st.session_state, mode_key)  # staged run supersedes displayed results
    pending[mode_key] = {"claims": claims, "evidence": evidence, "inputs": inputs,
                         "context": context or evidence}
    st.info("Live run prepared. Review the call count and confirm below. Nothing is billed yet.")


def _trace_save_attempt(mode: str, name: str, saved: str | None, error: str | None) -> None:
    """Append one line per Save click to a git-ignored trace log.

    Records mode, workspace name, and outcome only. Never evidence text,
    credentials, or report content. Best effort; failures stay silent.
    """
    try:
        runs_dir = _os.path.join(_PROJDIR, ".pruvchat_runs")
        _os.makedirs(runs_dir, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        outcome = f"OK file={_os.path.basename(saved)}" if saved else f"ERROR {error}"
        with open(_os.path.join(runs_dir, "save_trace.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} mode={mode} name={name} {outcome}\n")
    except Exception:
        pass


def _render_save_status(mode_key: str) -> None:
    """Show the last save outcome persistently until the next run."""
    status = get_save_status(st.session_state, mode_key)
    if not status:
        return
    if status["ok"]:
        st.info(f"Last save {status['at']}: {status['message']}. See Saved workspaces.")
    else:
        st.error(f"Last save {status['at']} failed: {status['message']}")


_MODE_PAGES = {"requirements": "Requirements", "disputes-a": "Business disputes",
               "disputes-b": "Business disputes", "custom": "Custom review", "visa": "Visa review"}
_MODE_INPUT_KEYS = {"requirements": {"requirements": "req_text", "evidence": "req_ev"},
                    "disputes-a": {"claim": "d_claim", "side_a": "d_a"},
                    "disputes-b": {"claim": "d_claim", "side_b": "d_b"},
                    "custom": {"objective": "c_obj", "claims": "c_claims", "evidence": "c_ev"},
                    "visa": {"requirements": "v_text", "source_name": "v_src",
                             "source_date": "v_date", "evidence": "v_ev"}}

# Overview cards in display order. Pages must stay registered in
# pruvcore.navigation PAGES; rendering filters to registered pages so a card
# can never request an unknown page.
_DASHBOARD_CARDS = (
    {"page": "Requirements", "title": "Requirements",
     "caption": "Review documents against criteria.",
     "button": "Explore Requirements", "key": "go_req"},
    {"page": "Business disputes", "title": "Business disputes",
     "caption": "Compare claims and evidence.",
     "button": "Explore Business disputes", "key": "go_dis"},
    {"page": "Custom review", "title": "Custom review",
     "caption": "Explore your own questions.",
     "button": "Explore Custom review", "key": "go_cus"},
    {"page": "Visa review", "title": "Visa review",
     "caption": "Check documents against official sources.",
     "button": "Explore Visa review", "key": "go_visa"},
)

_PURPOSES = ("Visit", "Work", "Study", "Join family", "Talent or specialist", "Other")
_PURPOSE_PRESETS = {"Visit": "UK Standard Visitor visa", "Work": "UK Skilled Worker visa",
                    "Study": "UK Student visa", "Join family": "UK Family visa",
                    "Talent or specialist": "UK Global Talent visa",
                    "Other": "Custom official URL"}
_MANUAL_ROUTE = "Manual verification required"
_UNSURE_ROUTE = "Not sure which route applies"
_CUSTOM_URL_ROUTE = "Custom official URL"


def _general_category(purpose: str) -> str:
    """General travel category label. Never a confirmed visa classification."""
    return f"{purpose} (general category)"


def _route_options_for(country: str, purpose: str) -> list:
    """Route labels for a destination and purpose. Pure function.

    Only UK presets name specific visas. Everywhere else the options are
    general categories or explicit manual paths, so the UI can never show
    an invented official route name.
    """
    if not country:
        return [_MANUAL_ROUTE, _UNSURE_ROUTE]
    if country == "United Kingdom":
        return [r["label"] for r in PRESET_ROUTES] + [_UNSURE_ROUTE, _CUSTOM_URL_ROUTE]
    if (purpose or "") in ("Visit", "Work", "Study", "Join family", "Talent or specialist"):
        return [_general_category(purpose), _UNSURE_ROUTE, _MANUAL_ROUTE]
    return [_UNSURE_ROUTE, _MANUAL_ROUTE]


def _default_route_for(country: str, purpose: str) -> str:
    """Route to select when the purpose changes. Resets stale routes."""
    if country == "United Kingdom":
        return _PURPOSE_PRESETS.get(purpose or "", _CUSTOM_URL_ROUTE)
    options = _route_options_for(country, purpose)
    return options[0] if options else _MANUAL_ROUTE


def _visa_progress() -> None:
    """Step indicator for the visa flow. Reads state only."""
    country = bool(st.session_state.get("v_country", ""))
    route = bool(st.session_state.get("v_route", "")) and country
    docs = bool((st.session_state.get("v_text", "") or "").strip())
    done = "results_visa" in st.session_state
    steps_done = sum([country, route, docs, done])
    current = min(steps_done + 1, 4)
    names = {1: "Choose your destination", 2: "Choose your route",
             3: "Add your documents", 4: "Review your results"}
    st.caption(f"Step {current} of 4: {names[current]}.")
    st.progress(steps_done / 4)


def _open_workspace(data: dict) -> None:
    """Restore a saved run into its mode page. Local only. No providers called."""
    restored = restore_workspace(data)
    mode = restored["mode"]
    if mode not in _MODE_PAGES:
        raise ValueError(f"unknown saved mode: {mode!r}")
    if _MODE_PAGES[mode] not in PAGES:
        raise ValueError(f"saved workspace needs page {_MODE_PAGES[mode]!r}, which is not "
                         "available. Please restart the app and open it again.")
    for field, session_key in _MODE_INPUT_KEYS[mode].items():
        if field in restored["inputs"]:
            st.session_state[session_key] = restored["inputs"][field]
    st.session_state["loaded_run"] = data
    clear_save_status(st.session_state, mode)
    if restored["legacy"] or not restored["assessments"]:
        clear_stored_results(st.session_state, mode)
        st.session_state[f"restore_notice_{mode}"] = True
    else:
        st.session_state.pop(f"restore_notice_{mode}", None)
        engine = _LIVE if restored["engine"] == "live" else _MOCK
        label = (f"assessed {restored['saved_at']} · {restored['engine']} engine · "
                 f"{restored['provider']}" + (f" ({restored['model']})" if restored["model"] else ""))
        stash_results(st.session_state, mode, restored["assessments"], restored["evidence"],
                      restored["inputs"], engine,
                      live_label=(f"{restored['model']} · restored"
                                  if restored["engine"] == "live" else None),
                      model=restored["model"], restored_label=label)
    request_nav(st.session_state, _MODE_PAGES[mode])


_search_open = st.session_state.pop("_search_open", None)
if _search_open is not None:
    try:
        _open_workspace(load_run(_PROJDIR, _search_open))
    except Exception as exc:
        st.error(f"Could not open: {exc}")
    else:
        st.rerun()


def _render_stored_results(mode_key: str) -> None:
    """Render stashed results on every rerun so Save/downloads always work."""
    job = take_stored_results(st.session_state, mode_key, st.session_state.get("engine", _MOCK))
    if job is None:
        job = take_restored_results(st.session_state, mode_key)
    if job is None:
        job = take_fallback_results(st.session_state, mode_key)
    if not job:
        if st.session_state.get(f"restore_notice_{mode_key}"):
            st.info("No saved assessment results. Run an assessment to make new findings.")
        return
    _render_results(job["results"], mode_key, job["evidence"], job["inputs"],
                    live_label=job.get("live_label"), model=job.get("model", ""),
                    restored_label=job.get("restored_label"), engine=job.get("engine"))


def _live_confirm_block(mode_key: str) -> None:
    """Always-rendered confirm gate for a staged live job. No auto-run, no retry."""
    job = st.session_state.get("live_pending", {}).get(mode_key)
    if not job:
        return
    model = st.session_state.get("live_model", "muse-spark-1.3")
    n_calls = len(job["claims"])
    st.warning(f"This will make {n_calls} paid Meta API call(s) "
               f"(`{model}`), one per claim. "
               f"Each call runs once. Failed claims are marked UNVERIFIED.")
    col_yes, col_no = st.columns(2)
    with col_yes:
        confirm = st.button("Confirm & run live (spend credits)", key=f"confirm_{mode_key}",
                            type="primary")
    with col_no:
        cancel = st.button("Cancel", key=f"cancel_{mode_key}")
    if cancel:
        st.session_state["live_pending"].pop(mode_key, None)
        st.rerun()
    if confirm:
        st.session_state["live_pending"].pop(mode_key, None)
        _execute_live(mode_key, job["claims"], job["evidence"], job["inputs"],
                      job.get("context") or job["evidence"])
        _render_stored_results(mode_key)


def _execute_live(mode_key: str, claims: list, evidence: list, inputs: dict,
                  context: list | None = None) -> None:
    """Run grounded live calls. Errors show as errors. They never become verdicts."""
    try:
        provider = get_provider("live", project_dir=_PROJDIR,
                                model=st.session_state.get("live_model"),
                                call_budget=len(claims))
    except ConfigError as exc:
        st.error(f"Live unavailable: {exc}")
        results = fallback_unverified(
            claims, f"live unavailable: {str(exc)[:300]}",
            method="live fallback: unverified (live unavailable)")
        _record_run(mode_key, summarize(results))
        stash_results(st.session_state, mode_key, results, evidence, inputs, _MOCK, fallback=True)
        return
    texts = [e.text for e in evidence]
    bar = st.progress(0, text=f"Calling {provider.model}…")
    results: list = []
    errors = 0
    for i, claim in enumerate(claims):
        try:
            out = provider.assess_claim(claim.text, texts)
        except ProviderError as exc:
            errors += 1
            st.error(f"Claim {claim.id}: live call failed ({exc}). "
                     "Recorded as UNVERIFIED below. Nothing was made up.")
            if provider.last_diagnostics:
                st.caption(f"Diagnostics (metadata only): {provider.last_diagnostics}")
            results.extend(fallback_unverified(
                [claim], f"live call failed: {str(exc)[:300]}",
                method="live fallback: unverified (live call failed)"))
            bar.progress((i + 1) / len(claims))
            continue
        try:
            verdict_raw = str(out.get("verdict", "")).strip().lower()
            verdict = Verdict(verdict_raw)
            ids = tuple(evidence[j].id for j in out.get("cited", ()))
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            errors += 1
            st.error(f"Claim {claim.id}: live response could not be used ({exc}). "
                     "Recorded as UNVERIFIED below. Nothing was made up.")
            results.extend(fallback_unverified(
                [claim], f"live response unusable: {str(exc)[:300]}",
                method="live fallback: unverified (unparseable live response)"))
            bar.progress((i + 1) / len(claims))
            continue
        if not ids and verdict is not Verdict.UNSUPPORTED:
            st.warning(f"Claim {claim.id} returned {verdict.value} with zero citations, "
                       "so it stays UNVERIFIED.")
            results.extend(fallback_unverified(
                [claim], f"live model returned {verdict.value} with zero citations.",
                method="live fallback: unverified (no citable evidence)"))
            bar.progress((i + 1) / len(claims))
            continue
        sent = out.get("sent") or ()
        omitted = out.get("omitted") or ()
        shortened = out.get("shortened") or 0
        ground_note = ""
        if omitted or shortened:
            total = len(sent) + len(omitted)
            ground_note = (f"; grounded in {len(sent)} of {total} items "
                           f"({len(omitted)} omitted, {shortened} shortened to fit)")
            st.caption(f"Claim {claim.id}: model reviewed {len(sent)} of {total} evidence items "
                       f"(ranked by relevance; {len(omitted)} omitted, "
                       f"{shortened} shortened by context budget).")
        results.append(Assessment(
            claim=claim, verdict=verdict,
            score={"supported": 1.0, "contested": 0.5, "unsupported": 0.0}[verdict_raw],
            rationale=str(out.get("rationale", "")), evidence_ids=ids,
            uncertainty=uncertainty_for(verdict, False),
            method=f"live Meta API ({provider.model}), no overlap score{ground_note}"))
        bar.progress((i + 1) / len(claims))
    spend = st.session_state.setdefault("live_spend", {"calls": 0, "usd": 0.0})
    spend["calls"] += len(provider.calls)
    spend["usd"] = round(spend["usd"] + provider.estimated_cost_usd(), 6)
    u = provider.usage_total
    st.caption(f"Live usage this run: {u['input_tokens']} in / {u['output_tokens']} out tokens · "
               f"≈${provider.estimated_cost_usd():.6f} (rough estimate, check your bill)")
    if not results:
        st.error("All live calls failed. Showing no verdicts. Check key, network, and credits.")
        return
    annotated = annotate_contradictions(results, list(context) if context else evidence)
    _record_run(mode_key, summarize(annotated))
    unverified = sum(1 for r in annotated if r.method.startswith("live fallback"))
    stash_results(st.session_state, mode_key, annotated, evidence, inputs,
                  st.session_state.get("engine", _MOCK),
                  live_label=(f"{provider.model} · {len(results)} live finding(s), "
                              f"{unverified} unverified, {errors} error(s)"),
                  model=provider.model)


_SIMPLE_LABEL = {"supported": "Supported", "contested": "Needs review",
                 "unsupported": "Missing"}


def _finding_card(card: dict, mode: str, provider_note: str | None = None) -> None:
    """Compact finding: title, status, one sentence, next action, details."""
    status = str(card.get("status", ""))
    st.subheader(card.get("title", "?"))
    st.write(f"**{_SIMPLE_LABEL.get(status, 'Needs review')}** · "
             f"Uncertainty: {card.get('uncertainty', '?')}")
    st.write(plain_verdict(status))
    st.write(f"Next action: {card.get('next_action', '')}")
    if card.get("contradicted_by"):
        st.warning("Contradiction flag (heuristic): other evidence disagrees. "
                   f"{', '.join(card['contradicted_by'])}. Treat this as a lead for review.")
    with st.expander("View evidence and details"):
        if not card.get("citations"):
            st.caption("No supporting evidence supplied.")
        for c in card.get("citations") or []:
            st.markdown(f"**{c.get('id', '?')}** · `{c.get('locator') or c.get('source', '')}`")
            st.markdown(to_blockquote(c.get("excerpt", "")))
        st.write(card.get("rationale", ""))
        method = str(card.get("method", ""))
        if method.startswith("live"):
            st.caption("Live verdict (no overlap score)")
        else:
            st.caption(f"Heuristic overlap: {card.get('score', '?')}")
        st.caption(f"Method: {method}")
        if mode == "visa":
            st.caption(f"Coverage: {coverage_for(status)}")
        if provider_note:
            st.caption(provider_note)


def _render_results(results: list, mode: str, evidence: list, inputs: dict,
                    live_label: str | None = None, model: str = "",
                    restored_label: str | None = None, engine: str | None = None) -> None:
    if not results:
        st.info("No claims to assess. Enter text or click Try example.")
        return
    if live_label:
        st.info(f"LIVE verdicts: {live_label}. Citations use only your evidence.")
    if restored_label:
        st.info(f"Restored saved findings: {restored_label}. No providers called.")
    if mode == "visa" and st.session_state.get("rereview_visa"):
        st.warning("Official sources changed since this review. Your checklist was kept as it was. "
                   "Please run the assessment again.")
    by_id = {e.id: e for e in evidence}
    cards = [assessment_to_card(r, by_id) for r in results]
    summary = summarize(results)
    flagged = sum(1 for r in results if r.contradicted_by)
    total = summary["total"]
    st.write(f"{total} finding{'s' if total != 1 else ''}: "
             f"{summary['supported']} Supported · {summary['contested']} Needs review · "
             f"{summary['unsupported']} Missing"
             + (f" · {flagged} flagged for disagreement." if flagged else "."))
    with st.expander("What these labels mean"):
        st.write("Supported: the evidence backs this claim.")
        st.write("Needs review: the evidence partly backs this claim or disagrees (contested).")
        st.write("Missing: no supporting evidence was found (unsupported).")
        st.write("Flagged: other evidence disagrees with this finding.")
    if mode == "visa":
        cov = coverage_summary(results)
        st.subheader("Step 4. Review your results")
        st.write(f"What looks ready: {cov['ready']} of {cov['total']} item(s) have supporting evidence on file.")
        st.write(f"What needs attention: {cov['needs_attention'] + cov['missing']} item(s) still need evidence or a closer look.")
        if cov["missing"] or cov["needs_attention"]:
            st.write("What to do next: add evidence for the flagged items, then run the assessment again.")
        else:
            st.write("What to do next: review each quoted source before you rely on this. Ready does not mean approved.")
        st.caption(COVERAGE_HELP)
    for card in cards:
        with st.container(border=True):
            note = _provider.generate(f"verify {card['claim'][:80]}")
            _finding_card(card, mode, provider_note=(
                "Separate quick signal (mock, first 80 characters only, "
                "not the finding above): "
                f"{note['model']} said {note['verdict']}. {note['rationale']}"))
    st.divider()
    st.subheader("Save or export")
    _render_save_status(mode)
    name = st.text_input("Workspace name", value=f"{mode}-{_dt.datetime.now().strftime('%m%d-%H%M')}",
                         key=f"save_name_{mode}")
    dl_engine = engine or st.session_state.get("engine", _MOCK)
    dl_tag = "live" if dl_engine == _LIVE else "mock"
    dl_header = f"# PruvChat findings: {_MODE_PAGES.get(mode, mode)}\nEngine: {dl_engine}"
    if live_label:
        dl_header += f"\nRun: {live_label}"
    if restored_label:
        dl_header += f"\nRestored: {restored_label} (no providers called)"
    if mode == "visa":
        dl_header += (f"\nChecklist source: {inputs.get('source_name') or 'not stated'}"
                      f" ({inputs.get('source_date') or 'no date given'})")
        for src in unpack_sources(inputs):
            dl_header += (f"\nOfficial source: {src.get('title') or src.get('final_url') or src.get('url')}"
                          f" · {src.get('final_url') or src.get('url')}"
                          f" · retrieved {src.get('retrieved_at') or '?'}"
                          f" · {src.get('status') or '?'}")
        dl_header += f"\nCoverage: {coverage_line(coverage_summary(results))}"
        dl_header += f"\nSafety: {SAFETY_NOTE}"
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Save workspace locally", key=f"save_{mode}"):
            saved = None
            save_error = None
            save_engine = engine or st.session_state.get("engine", _MOCK)
            save_provider = "meta-live" if save_engine == _LIVE else "mock"
            try:
                saved = save_run(_PROJDIR, name, mode, inputs, cards, summary,
                                 engine="live" if save_engine == _LIVE else "mock",
                                 provider=save_provider, model=model)
            except Exception as exc:
                save_error = f"{type(exc).__name__}: {exc}"
            _trace_save_attempt(mode, name, saved, save_error)
            if save_error is not None:
                set_save_status(st.session_state, mode, False, save_error)
                st.error(f"Could not save: {save_error}")
            else:
                set_save_status(st.session_state, mode, True, name)
                st.success("Saved successfully.")
                st.rerun()
    with col_b:
        st.download_button("Download findings (.md)",
                           assessments_to_markdown(results, by_id, header=dl_header),
                           file_name=f"pruvchat_{mode}_{dl_tag}_report.md", key=f"dl_md_{mode}")
    with col_c:
        full = export_report({"name": name, "mode": mode, "saved_at": "unsaved draft",
                              "engine": "live" if dl_tag == "live" else "mock",
                              "provider": "meta-live" if dl_tag == "live" else "mock",
                              "model": model, "summary": summary, "cards": cards})
        if mode == "visa":
            full += f"\n\nCoverage: {coverage_line(coverage_summary(results))}"
            full += f"\nSafety: {SAFETY_NOTE}"
            for src in unpack_sources(inputs):
                full += (f"\nOfficial source: {src.get('title') or src.get('url')}"
                         f" · {src.get('final_url') or src.get('url')}"
                         f" · retrieved {src.get('retrieved_at') or '?'}")
        st.download_button("Download full report (.md)", full,
                           file_name=f"pruvchat_{mode}_{dl_tag}_full.md", key=f"dl_full_{mode}")


mode = st.session_state.get("nav", PAGES[0])
_saved = list_runs(_PROJDIR)
st.sidebar.subheader(f"Saved workspaces ({len(_saved)} on this machine)")
if _saved:
    labels = {f"{r['name']} ({r['mode']}) · {r['saved_at']}": r["file"] for r in _saved}
    pick = st.sidebar.selectbox("Open a saved run", list(labels), key="open_pick")
    col_open, col_del = st.sidebar.columns(2)
    with col_open:
        if st.button("Open", key="open_btn"):
            try:
                _open_workspace(load_run(_PROJDIR, labels[pick]))
            except Exception as exc:
                st.sidebar.error(f"Could not open: {exc}")
            else:
                st.rerun()
    with col_del:
        if st.button("Delete", key="del_btn"):
            delete_run(_PROJDIR, labels[pick])
            st.session_state.pop("loaded_run", None)
            st.rerun()
else:
    st.sidebar.caption("No saved runs yet. Runs save to .pruvchat_runs/ (kept out of git).")

if mode == "Overview":
    st.header("Your evidence workspace")
    st.write("Choose what you want to check.")
    if not st.session_state.get("hide_guide"):
        with st.container(border=True):
            st.subheader("Understand your workspace")
            st.write("1. Choose what you want to check.")
            st.write("2. Add documents or an official source.")
            st.write("3. Review findings and missing evidence.")
            st.write("4. Save or export your results.")
            _g1, _g2 = st.columns(2)
            with _g1:
                if st.button("Skip", key="guide_skip", type="tertiary"):
                    st.session_state["hide_guide"] = True
                    st.rerun()
            with _g2:
                if st.button("Close", key="guide_close", type="tertiary"):
                    st.session_state["hide_guide"] = True
                    st.rerun()
    cards = [c for c in _DASHBOARD_CARDS if c["page"] in PAGES]
    for row in (cards[0:2], cards[2:4]):
        cols = st.columns(2)
        for col, card in zip(cols, row):
            with col:
                with st.container(border=True):
                    st.subheader(card["title"])
                    st.caption(card["caption"])
                    if st.button(card["button"], key=card["key"], type="tertiary"):
                        request_nav(st.session_state, card["page"])
                        st.rerun()
    st.divider()
    loaded = st.session_state.get("loaded_run")
    if loaded:
        st.subheader(f"Saved workspace: {loaded.get('name', '?')}")
        st.caption(f"Mode: {loaded.get('mode', '?')} · Saved: {loaded.get('saved_at', '?')}")
        st.download_button("Download saved report (.md)", export_report(loaded),
                           file_name=f"pruvchat_{loaded.get('name', 'run')}.md", key="dl_saved")
        for card in loaded.get("cards") or []:
            with st.container(border=True):
                _finding_card(card, str(loaded.get("mode", "")))
    else:
        with st.expander("How a run works"):
            st.write("1. Add evidence. Paste text, upload files (TXT, MD, PDF, or DOCX), or fetch a public link.\n"
                     "2. Run the assessment. Watch each step as it runs.\n"
                     "3. Read your PruvCards. Each verdict shows quotes, flags, and next steps.\n"
                     "4. Save your workspace on this machine, or export it as a report.")
        with st.expander("Limitations you should know"):
            st.write("- Mock verdicts compare shared words, not truth. Always review the sources.\n"
                     "- Scanned PDFs need OCR to read text from images. It is not included, so they report no text.\n"
                     "- URL fetching only opens public pages. It cannot use logins or private drives.\n"
                     "- Nothing leaves this machine except pages you choose to fetch.")

if mode == "Requirements":
    st.header("Requirements")
    st.caption("One requirement per line. Uploaded files and fetched pages join pasted evidence.")
    if st.button("Try example"):
        fix = _load_fixture("requirements_review.json")
        st.session_state["req_text"] = "\n".join(i["requirement"] for i in fix["items"])
        st.session_state["req_ev"] = "\n".join(e["text"] for i in fix["items"] for e in i["evidence"])
        clear_stored_results(st.session_state, "requirements")
    st.caption("Try example loads synthetic demo data (fictional, for testing only).")
    st.text_area("Requirements", key="req_text", height=140, placeholder="Paste requirements, one per line…")
    uploads = st.file_uploader("Evidence files (.txt/.md/.pdf/.docx)", type=["txt", "md", "pdf", "docx"],
                               accept_multiple_files=True)
    st.text_area("Evidence (one item per line)", key="req_ev", height=140, placeholder="Paste evidence lines…",
                  help="One item per line. Citations quote these exact lines.")
    web_ev = _fetch_panel("req")
    if st.button("Run assessment", type="primary",
                   help="Run the assessment with the current inputs."):
        reqs = [ln.strip() for ln in st.session_state.get("req_text", "").splitlines() if ln.strip()]
        ev = _evin(st.session_state.get("req_ev", ""), "e")
        for n, d in enumerate(read_uploads(uploads)):
            if d.warning:
                st.warning(f"{d.name}: {d.warning}")
            if d.text.strip():
                ev.append(EvidenceRef(id=f"u{n + 1}", text=d.text, source="upload",
                                      locator=f"upload:{d.name}"))
        ev.extend(web_ev)
        _dispatch_assessment("requirements",
                             [Claim(id=f"r{i + 1}", text=t) for i, t in enumerate(reqs)], ev,
                             {"requirements": st.session_state.get("req_text", ""),
                              "evidence": st.session_state.get("req_ev", "")})
    _render_stored_results("requirements")
    _live_confirm_block("requirements")

elif mode == "Business disputes":
    st.header("Business disputes")
    st.caption("See how each side's evidence supports the same claim.")
    if st.button("Try example"):
        fix = _load_fixture("business_dispute.json")
        st.session_state["d_claim"] = fix["claim"]
        st.session_state["d_a"] = "\n".join(e["text"] for e in fix["side_a"]["evidence"])
        st.session_state["d_b"] = "\n".join(e["text"] for e in fix["side_b"]["evidence"])
        clear_stored_results(st.session_state, "disputes-a")
        clear_stored_results(st.session_state, "disputes-b")
    st.caption("Try example loads synthetic demo data (fictional, for testing only).")
    st.text_area("Claim under review", key="d_claim", height=80)
    col_a, col_b = st.columns(2)
    with col_a:
        st.text_area("Side A evidence (Buyer)", key="d_a", height=140)
    with col_b:
        st.text_area("Side B evidence (Seller)", key="d_b", height=140)
    if st.button("Run assessment", type="primary",
                   help="Run the assessment with the current inputs."):
        claim = Claim(id="d1", text=st.session_state.get("d_claim", ""))
        ev_a = _evin(st.session_state.get("d_a", ""), "a", source="side-a", locator="side A")
        ev_b = _evin(st.session_state.get("d_b", ""), "b", source="side-b", locator="side B")
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Against Side A")
            _dispatch_assessment("disputes-a", [claim], ev_a,
                                 {"claim": claim.text, "side_a": st.session_state.get("d_a", "")},
                                 context=ev_a + ev_b)
        with col_b:
            st.subheader("Against Side B")
            _dispatch_assessment("disputes-b", [claim], ev_b,
                                 {"claim": claim.text, "side_b": st.session_state.get("d_b", "")},
                                 context=ev_a + ev_b)
    _render_stored_results("disputes-a")
    _render_stored_results("disputes-b")
    _live_confirm_block("disputes-a")
    _live_confirm_block("disputes-b")

elif mode == "Visa review":
    st.header("Visa review")
    st.caption("Choose your destination and route, add your documents, then review the results.")
    _visa_progress()
    st.info(SAFETY_NOTE)
    st.subheader("Step 1. Choose your destination")
    _visa_country_picker()
    country = st.session_state.get("v_country", "")
    st.subheader("Step 2. Choose your route")
    purpose = st.radio("Purpose of travel", list(_PURPOSES), key="v_purpose",
                       help="What best describes this trip? Changing it resets the route below.")
    if "v_purpose_applied" not in st.session_state:
        st.session_state["v_purpose_applied"] = purpose
    elif st.session_state["v_purpose_applied"] != purpose:
        st.session_state["v_purpose_applied"] = purpose
        st.session_state["v_route"] = _default_route_for(country, purpose)
    route_options = _route_options_for(country, purpose)
    if st.session_state.get("v_route") not in route_options:
        st.session_state["v_route"] = route_options[0]
    route = st.selectbox("Visa route", route_options, key="v_route",
                         help="Routes for this destination and purpose. Unverified routes stay manual.")
    st.caption("Country alone does not set the route. Citizenship, residence, "
               "and travel history can also matter.")
    preset = next((r for r in PRESET_ROUTES if r["label"] == route), None)
    preset_url = preset["url"] if preset else ""
    if preset and preset.get("note"):
        st.caption(preset["note"])
    if preset is None and route != _CUSTOM_URL_ROUTE:
        portal = COUNTRY_PORTALS.get(country, {}) if country else {}
        if route == _general_category(purpose):
            st.caption(f"{route} for {country} is a general travel category, not a confirmed "
                       "visa classification. Confirm the exact route on the official site.")
        elif route == _UNSURE_ROUTE:
            st.caption("Not sure is fine. Start from the official portal below and confirm "
                       "which route fits before fetching.")
        else:
            st.warning(f"No verified checklist for {purpose} travel to {country} yet. "
                       "We do not guess checklists.")
        if portal:
            st.link_button(f"Open {portal['name']}", portal["url"],
                           help="Open the official immigration site in a new tab.")
        elif country:
            st.caption("No verified portal link for this destination yet. Find the official "
                       "immigration site yourself and paste its address below.")
        else:
            st.caption("Pick a destination above first, then confirm the route.")
        st.caption("Paste the requirements from the official site below, or fetch an official "
                   "page address, then continue as usual.")
    st.subheader("Official immigration source")
    st.caption("Fetches one official page when you click. Confirm the address first. "
               "Applicant documents never leave this machine.")
    if preset_url:
        st.caption(f"Preset address: {preset_url}. Please confirm it before fetching.")
        if st.button("Use preset address"):
            st.session_state["official_url_visa"] = preset_url
    else:
        st.text_input("Route name", key="v_route_name",
                      placeholder="Name this route, for example Family visit")
    st.text_input("Official URL", key="official_url_visa",
                  placeholder="https://www.gov.uk/standard-visitor-visa",
                  help="Paste the exact official page address, then click Fetch.")
    if st.button("Fetch official source", key="fetch_official_visa",
                   help="Fetch one official page. Documents never leave this machine."):
        url = (st.session_state.get("official_url_visa") or "").strip() or preset_url
        if not url:
            st.error("Enter an official URL first.")
        else:
            route_label = route
            if not preset_url:
                route_label = (st.session_state.get("v_route_name") or "").strip()
                if not route_label:
                    if route == _general_category(purpose):
                        route_label = f"{purpose} to {country} (general category)"
                    elif route == _UNSURE_ROUTE:
                        route_label = f"{purpose} to {country} (route unsure)"
                    elif route == _MANUAL_ROUTE:
                        route_label = f"{purpose} to {country} (manual verification)"
                    else:
                        route_label = "Custom route"
            with st.spinner("Fetching with safety checks…"):
                rec = request_source(url, route_label,
                                     st.session_state.setdefault("official_fetch_times", {}))
            if rec["status"] == "error":
                st.error(f"Could not fetch this source: {rec['reason']}")
            else:
                records = [r for r in st.session_state.get("official_records_visa", [])
                           if r.get("final_url") != rec["final_url"]]
                records.append(rec)
                st.session_state["official_records_visa"] = records
                st.session_state["official_candidates_visa"] = extract_candidates(
                    rec.get("full_text", ""), rec["id"],
                    rec.get("final_url") or rec.get("url"))
                for cand_key in [k for k in st.session_state if k.startswith("vcand_")]:
                    st.session_state.pop(cand_key, None)
                st.session_state.pop("refresh_notice_visa", None)
                st.success(f"Fetched: {rec['title'] or rec['final_url']}")
    _render_official_sources()
    st.subheader("Step 3. Add your documents")
    if st.button("Try example"):
        fix = _load_fixture("visa_checklist.json")
        st.session_state["v_text"] = "\n".join(i["requirement"] for i in fix["items"])
        st.session_state["v_src"] = fix.get("source_name", "")
        st.session_state["v_date"] = fix.get("source_date", "")
        st.session_state["v_ev"] = "\n".join(e["text"] for i in fix["items"] for e in i["evidence"])
        clear_stored_results(st.session_state, "visa")
    st.caption("Try example loads synthetic demo data (fictional, for testing only).")
    if st.button("Try Global Talent demo"):
        fix = _load_fixture("visa_global_talent.json")
        st.session_state["v_text"] = "\n".join(i["requirement"] for i in fix["items"])
        st.session_state["v_src"] = fix.get("source_name", "")
        st.session_state["v_date"] = fix.get("source_date", "")
        st.session_state["v_ev"] = "\n".join(e["text"] for i in fix["items"] for e in i["evidence"])
        clear_stored_results(st.session_state, "visa")
    st.caption("Global Talent demo is a fictional case for judges. No real applicant data.")
    st.text_area("Document items (one per line)", key="v_text", height=140,
                 placeholder="Paste document items, one per line…",
                 help="One document item per line. Each item is checked against your evidence.")
    with st.expander("Source details (recommended)"):
        st.text_input("Official source name", key="v_src",
                      placeholder="Name of the checklist or office this came from")
        st.text_input("Source date", key="v_date",
                      placeholder="Date shown on the source, if any")
    uploads = st.file_uploader("Evidence files (.txt/.md/.pdf/.docx)", type=["txt", "md", "pdf", "docx"],
                               accept_multiple_files=True)
    st.text_area("Evidence (one item per line)", key="v_ev", height=140,
                 placeholder="Paste evidence lines…",
                 help="One item per line. Citations quote these exact lines.")
    if st.button("Run assessment", type="primary",
                   help="Check each item against your evidence."):
        st.session_state.pop("rereview_visa", None)
        reqs = [ln.strip() for ln in st.session_state.get("v_text", "").splitlines() if ln.strip()]
        ev = _evin(st.session_state.get("v_ev", ""), "e", source="pasted note",
                   locator="pasted note")
        for n, d in enumerate(read_uploads(uploads)):
            if d.warning:
                st.warning(f"{d.name}: {d.warning}")
            if d.text.strip():
                ev.append(EvidenceRef(id=f"u{n + 1}", text=d.text, source="uploaded file",
                                      locator=f"upload:{d.name}"))
        _dispatch_assessment("visa",
                             [Claim(id=f"v{i + 1}", text=t) for i, t in enumerate(reqs)], ev,
                             {"requirements": st.session_state.get("v_text", ""),
                              "source_name": st.session_state.get("v_src", ""),
                              "source_date": st.session_state.get("v_date", ""),
                              "evidence": st.session_state.get("v_ev", ""),
                              **pack_sources(st.session_state.get("official_records_visa", []))})
    _render_stored_results("visa")
    _live_confirm_block("visa")

else:
    st.header("Custom review")
    st.caption("Your own claims plus evidence. You can also fetch a public link.")
    if st.button("Try example"):
        fix = _load_fixture("custom_assessment.json")
        st.session_state["c_claims"] = "\n".join(fix["claims"])
        st.session_state["c_ev"] = "\n".join(e["text"] for e in fix["evidence"])
        clear_stored_results(st.session_state, "custom")
    st.caption("Try example loads synthetic demo data (fictional, for testing only).")
    st.text_area("Objective", value="Verify the claims below against the evidence.", key="c_obj", height=60,
                  help="The question this review must answer.")
    st.text_area("Claims (one per line)", key="c_claims", height=120)
    st.text_area("Evidence (one item per line)", key="c_ev", height=120,
                  help="One item per line. Citations quote these exact lines.")
    web_ev = _fetch_panel("custom")
    if st.button("Run assessment", type="primary",
                   help="Run the assessment with the current inputs."):
        claim_lines = [ln.strip() for ln in st.session_state.get("c_claims", "").splitlines()
                       if ln.strip()]
        claims = [Claim(id=f"c{i + 1}", text=t) for i, t in enumerate(claim_lines)]
        ev = _evin(st.session_state.get("c_ev", ""), "e")
        ev.extend(web_ev)
        _dispatch_assessment("custom", claims, ev,
                             {"objective": st.session_state.get("c_obj", ""),
                              "claims": st.session_state.get("c_claims", ""),
                              "evidence": st.session_state.get("c_ev", "")})
    _render_stored_results("custom")
    _live_confirm_block("custom")

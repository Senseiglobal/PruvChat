"""PruvChat Phase 2 — evidence intelligence workspace (mock assessment core).

Verdicts are deterministic keyword-overlap heuristics, never AI judgments.
URL retrieval fetches public documents only (SSRF-guarded); saved runs stay
on this machine under .pruvchat_runs/.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os

import streamlit as st

from providers.meta_mock import MockMetaProvider
from pruvcards.render import assessment_to_card, assessments_to_markdown, summarize
from pruvcore.pipeline import annotate_contradictions, assess, extract_claims
from pruvcore.schemas import Claim, EvidenceRef
from pruvcore.store import delete_run, export_report, list_runs, load_run, save_run
from pruvfetch.fetch import fetch_url
from pruvfetch.uploads import read_uploads
from pruvfetch.urls import validate_url

st.set_page_config(page_title="PruvChat", layout="wide")
st.title("PruvChat")
st.caption("Evidence intelligence workspace — turn scattered documents into grounded findings.")
st.warning(
    "MOCK MODE — verdicts are keyword-overlap heuristics, not AI judgments. "
    "URL fetching contacts public sites only when you click Fetch. "
    "Saved runs stay on this machine."
)

_PROJDIR = _os.path.dirname(_os.path.abspath(__file__))
_FIXDIR = _os.path.join(_PROJDIR, "fixtures")
_provider = MockMetaProvider()


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
        st.write(f"Step 1/3 — extracted {len(claims)} claim(s).")
        results = assess(claims, evidence)
        st.write(f"Step 2/3 — scored against {len(evidence)} evidence item(s).")
        annotated = annotate_contradictions(results, list(context) if context else evidence)
        flagged = sum(1 for r in annotated if r.contradicted_by)
        st.write(f"Step 3/3 — contradiction check flagged {flagged} claim(s).")
        status.update(label="Assessment complete", state="complete")
    return annotated


def _fetch_panel(key: str) -> list:
    """Opt-in public-URL retrieval; returns fetched evidence (may be empty)."""
    st.subheader("Add a public document by URL")
    st.caption("Public links only — localhost, private networks, and logins are blocked.")
    url = st.text_input("Document URL", key=f"url_{key}", placeholder="https://example.com/spec")
    use = st.checkbox("Use fetched text as evidence", value=True, key=f"use_{key}")
    if not st.button("Fetch public document", key=f"fetch_{key}"):
        return []
    if not url:
        st.error("Enter a URL first.")
        return []
    with st.spinner("Fetching with safety checks…"):
        doc = fetch_url(url)
    if doc.warning and not doc.text:
        st.error(f"Fetch blocked or failed: {doc.warning}")
        return []
    st.success(f"Fetched {doc.size_bytes} bytes — {doc.content_type or 'unknown type'}")
    st.caption(f"Source: {doc.final_url} · HTTP {doc.status} · retrieved {doc.fetched_at}"
               + (f" · WARNING: {doc.warning}" if doc.warning else "")
               + (" · truncated at cap" if doc.truncated else ""))
    if not use or not doc.text.strip():
        return []
    paras = [p.strip() for p in doc.text.splitlines() if p.strip()][:40]
    return [EvidenceRef(id=f"w{i + 1}", text=p, source="url", locator=f"url:{doc.final_url}")
            for i, p in enumerate(paras)]


def _render_results(results: list, mode: str, evidence: list, inputs: dict) -> None:
    if not results:
        st.info("No claims to assess. Enter text or load the sample fixture.")
        return
    by_id = {e.id: e for e in evidence}
    cards = [assessment_to_card(r, by_id) for r in results]
    summary = summarize(results)
    flagged = sum(1 for r in results if r.contradicted_by)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Supported", summary["supported"])
    c2.metric("Contested", summary["contested"])
    c3.metric("Unproven", summary["unsupported"])
    c4.metric("Flagged", flagged)
    c5.metric("Total", summary["total"])
    for card in cards:
        with st.container(border=True):
            st.subheader(card["title"])
            badge = {"supported": st.success, "contested": st.warning,
                     "unsupported": st.error}[card["status"]]
            badge(f"Status: {card['status'].upper()}  |  Heuristic overlap: {card['score']}  |  "
                  f"Uncertainty: {card['uncertainty']}")
            st.write(card["rationale"])
            if card["contradicted_by"]:
                st.warning("Contradiction flag (heuristic): other evidence disagrees — "
                           f"{', '.join(card['contradicted_by'])}. Treat as a lead for review.")
            with st.expander(f"Evidence ({len(card['citations'])} ref(s))", expanded=bool(card["citations"])):
                if not card["citations"]:
                    st.caption("No supporting evidence supplied.")
                for c in card["citations"]:
                    st.markdown(f"**{c['id']}** · `{c['locator'] or c['source']}`")
                    st.quote(c["excerpt"] or "(no excerpt)")
            st.caption(f"Next action: {card['next_action']}")
            st.caption(f"Method: {card['method']}")
            with st.expander("Provider note (mock)"):
                note = _provider.generate(f"verify {card['claim'][:80]}")
                st.write(f"{note['model']}: {note['verdict']} — {note['rationale']}")
    st.divider()
    st.subheader("Save or export")
    name = st.text_input("Workspace name", value=f"{mode}-{_dt.datetime.now().strftime('%m%d-%H%M')}",
                         key=f"save_name_{mode}")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Save workspace locally", key=f"save_{mode}"):
            try:
                path = save_run(_PROJDIR, name, mode, inputs, cards, summary)
                st.success(f"Saved: {_os.path.basename(path)}")
            except Exception as exc:
                st.error(f"Could not save: {exc}")
    with col_b:
        st.download_button("Download findings (.md)", assessments_to_markdown(results, by_id),
                           file_name=f"pruvchat_{mode}_mock_report.md", key=f"dl_md_{mode}")
    with col_c:
        st.download_button("Download full report (.md)",
                           export_report({"name": name, "mode": mode, "saved_at": "unsaved draft",
                                          "summary": summary, "cards": cards}),
                           file_name=f"pruvchat_{mode}_mock_full.md", key=f"dl_full_{mode}")
    _record_run(mode, summary)


if "nav" not in st.session_state:
    st.session_state["nav"] = "Dashboard"
mode = st.sidebar.radio("Workspace", ["Dashboard", "Requirements review", "Business disputes", "Custom"],
                        key="nav")
st.sidebar.divider()
st.sidebar.subheader("Saved workspaces (this machine)")
_saved = list_runs(_PROJDIR)
if _saved:
    labels = {f"{r['saved_at']} · {r['name']} ({r['mode']})": r["file"] for r in _saved}
    pick = st.sidebar.selectbox("Open a saved run", list(labels), key="open_pick")
    col_open, col_del = st.sidebar.columns(2)
    with col_open:
        if st.button("Open", key="open_btn"):
            try:
                st.session_state["loaded_run"] = load_run(_PROJDIR, labels[pick])
                st.session_state["nav"] = "Dashboard"
                st.rerun()
            except Exception as exc:
                st.sidebar.error(f"Could not open: {exc}")
    with col_del:
        if st.button("Delete", key="del_btn"):
            delete_run(_PROJDIR, labels[pick])
            st.session_state.pop("loaded_run", None)
            st.rerun()
else:
    st.sidebar.caption("No saved runs yet. Runs save to .pruvchat_runs/ (git-ignored).")
st.sidebar.divider()
st.sidebar.subheader("Recent runs (this session)")
for run in reversed(st.session_state.get("runs", [])):
    st.sidebar.caption(
        f"{run['time']} {run['mode']}: "
        f"{run['supported']}S/{run['contested']}C/{run['unsupported']}U"
    )

if mode == "Dashboard":
    st.header("Welcome to your evidence workspace")
    st.write("Pick a starting point. Each mode runs the same evidence engine and produces "
             "PruvCards with exact source references, contradiction flags, and next actions.")
    m1, m2, m3 = st.columns(3)
    with m1:
        with st.container(border=True):
            st.subheader("Requirements review")
            st.caption("Check a submission against published criteria.")
            if st.button("Open requirements", key="go_req"):
                st.session_state["nav"] = "Requirements review"
                st.rerun()
    with m2:
        with st.container(border=True):
            st.subheader("Business disputes")
            st.caption("Compare two sides against the same claim.")
            if st.button("Open disputes", key="go_dis"):
                st.session_state["nav"] = "Business disputes"
                st.rerun()
    with m3:
        with st.container(border=True):
            st.subheader("Custom assessment")
            st.caption("Define your own objective and criteria.")
            if st.button("Open custom", key="go_cus"):
                st.session_state["nav"] = "Custom"
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
                st.subheader(card.get("title", "?"))
                st.write(f"Status: **{str(card.get('status', '?')).upper()}** · "
                         f"Uncertainty: {card.get('uncertainty', '?')}")
                st.write(card.get("rationale", ""))
                for c in card.get("citations") or []:
                    st.markdown(f"**{c.get('id', '?')}** · `{c.get('locator', '')}`")
                    st.quote(c.get("excerpt", ""))
                st.caption(f"Next action: {card.get('next_action', '')}")
    else:
        st.subheader("How a run works")
        st.write("1. Add evidence — paste text, upload TXT/MD/PDF/DOCX, or fetch a public URL.\n"
                 "2. Run the assessment — staged progress shows extraction, scoring, and checks.\n"
                 "3. Review PruvCards — verdicts with excerpts, flags, and next actions.\n"
                 "4. Save the workspace locally or export a Markdown report.")
        with st.expander("Limitations you should know"):
            st.write("- Mock verdicts measure keyword overlap, not truth — always review sources.\n"
                     "- Scanned PDFs need OCR, which is not included; they report no text.\n"
                     "- URL fetching is limited to public pages (no logins, no private drives).\n"
                     "- Nothing leaves this machine except pages you explicitly fetch.")

if mode == "Requirements review":
    st.header("Requirements review")
    st.caption("One requirement per line. Uploaded files and fetched pages join pasted evidence.")
    if st.button("Load sample fixture"):
        fix = _load_fixture("requirements_review.json")
        st.session_state["req_text"] = "\n".join(i["requirement"] for i in fix["items"])
        st.session_state["req_ev"] = "\n".join(e["text"] for i in fix["items"] for e in i["evidence"])
    st.text_area("Requirements", key="req_text", height=140, placeholder="Paste requirements, one per line…")
    uploads = st.file_uploader("Evidence files (.txt/.md/.pdf/.docx)", type=["txt", "md", "pdf", "docx"],
                               accept_multiple_files=True)
    st.text_area("Evidence (one item per line)", key="req_ev", height=140, placeholder="Paste evidence lines…")
    web_ev = _fetch_panel("req")
    if st.button("Run assessment", type="primary"):
        reqs = [ln.strip() for ln in st.session_state.get("req_text", "").splitlines() if ln.strip()]
        ev = _evin(st.session_state.get("req_ev", ""), "e")
        for n, d in enumerate(read_uploads(uploads)):
            if d.warning:
                st.warning(f"{d.name}: {d.warning}")
            if d.text.strip():
                ev.append(EvidenceRef(id=f"u{n + 1}", text=d.text, source="upload",
                                      locator=f"upload:{d.name}"))
        ev.extend(web_ev)
        results = _assess_staged([Claim(id=f"r{i + 1}", text=t) for i, t in enumerate(reqs)], ev)
        _render_results(results, "requirements", ev,
                        {"requirements": st.session_state.get("req_text", ""),
                         "evidence": st.session_state.get("req_ev", "")})

elif mode == "Business disputes":
    st.header("Business disputes")
    st.caption("Same claim text is scored against each side's evidence to surface disagreement.")
    if st.button("Load sample fixture"):
        fix = _load_fixture("business_dispute.json")
        st.session_state["d_claim"] = fix["claim"]
        st.session_state["d_a"] = "\n".join(e["text"] for e in fix["side_a"]["evidence"])
        st.session_state["d_b"] = "\n".join(e["text"] for e in fix["side_b"]["evidence"])
    st.text_area("Claim under review", key="d_claim", height=80)
    col_a, col_b = st.columns(2)
    with col_a:
        st.text_area("Side A evidence (Buyer)", key="d_a", height=140)
    with col_b:
        st.text_area("Side B evidence (Seller)", key="d_b", height=140)
    if st.button("Run assessment", type="primary"):
        claim = Claim(id="d1", text=st.session_state.get("d_claim", ""))
        ev_a = _evin(st.session_state.get("d_a", ""), "a", source="side-a", locator="side A")
        ev_b = _evin(st.session_state.get("d_b", ""), "b", source="side-b", locator="side B")
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Against Side A")
            _render_results(_assess_staged([claim], ev_a, ev_a + ev_b), "disputes-a", ev_a,
                            {"claim": claim.text, "side_a": st.session_state.get("d_a", "")})
        with col_b:
            st.subheader("Against Side B")
            _render_results(_assess_staged([claim], ev_b, ev_a + ev_b), "disputes-b", ev_b,
                            {"claim": claim.text, "side_b": st.session_state.get("d_b", "")})

else:
    st.header("Custom assessment")
    st.caption("Free-form claims plus evidence, with optional public-URL retrieval.")
    if st.button("Load sample fixture"):
        fix = _load_fixture("custom_assessment.json")
        st.session_state["c_claims"] = "\n".join(fix["claims"])
        st.session_state["c_ev"] = "\n".join(e["text"] for e in fix["evidence"])
    st.text_area("Objective", value="Verify the claims below against the evidence.", key="c_obj", height=60)
    st.text_area("Claims (one per line)", key="c_claims", height=120)
    st.text_area("Evidence (one item per line)", key="c_ev", height=120)
    web_ev = _fetch_panel("custom")
    if st.button("Run assessment", type="primary"):
        claims = extract_claims(" ".join(st.session_state.get("c_claims", "").splitlines()))
        ev = _evin(st.session_state.get("c_ev", ""), "e")
        ev.extend(web_ev)
        results = _assess_staged(claims, ev)
        _render_results(results, "custom", ev,
                        {"objective": st.session_state.get("c_obj", ""),
                         "claims": st.session_state.get("c_claims", ""),
                         "evidence": st.session_state.get("c_ev", "")})

st.divider()
st.caption("PruvChat mock build — verdicts are keyword heuristics. Always review the cited sources.")

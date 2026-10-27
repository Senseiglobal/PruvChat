# PruvChat Demo Script (Phase 1, ~2 minutes, fully offline)

Prereqs: `pip install -r requirements.txt`, then `streamlit run app.py`.

## 0:00 — Banner (10s)

Point at the `MOCK MODE — offline, no live API calls` banner. Everything after this
runs without network.

## 0:10 — Mode 1: Requirements review (40s)

1. Sidebar: select **Requirements review**.
2. Click **Load sample fixture** (loads `fixtures/requirements_review.json` text).
3. Click **Run assessment**.
4. Show the verdict cards: one SUPPORTED, one CONTESTED, one UNSUPPORTED with
   rationale + score. Expand one card's evidence line.

## 0:50 — Mode 2: Business disputes (40s)

1. Sidebar: select **Business disputes**.
2. Click **Load sample fixture** (loads `fixtures/business_dispute.json` sides A/B).
3. Click **Run assessment**.
4. Show side-by-side cards: same claim text scored against opposing evidence flips
   the verdict — the mock keyword overlap makes this visible and explainable.

## 1:30 — Mode 3: Custom + safe URL (30s)

1. Sidebar: select **Custom**.
2. Paste any sentence; add evidence; paste `https://example.com/spec`.
3. Click **Run assessment**. URL panel shows `fetched=false (mock stub)` —
   validated, never fetched live.

## 2:00 — Close (10s)

`pytest -q` passes offline; `providers/meta_mock.py` is the seam where the live
Meta Model API provider plugs in for Phase 2.

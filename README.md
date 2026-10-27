# PruvChat — Phase 2 Evidence Workspace (Mock Verdicts)

Working prototype. Assessments run through a deterministic mock pipeline plus a mock
Meta provider — no live API calls without explicit approval, no secrets logged.
Uploads (TXT/MD/PDF/DOCX), opt-in public-URL retrieval, and local run workspaces
are real; verdicts are keyword-overlap heuristics, not AI judgments.

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Requires Python 3.12+ (prototype targets 3.12-compatible syntax; verified here on 3.14).

## Modes

- **Requirements review** — paste or upload requirements text, get per-requirement check cards.
- **Business disputes** — paste each side's statement, get a side-by-side assessment.
- **Custom** — free-form text plus optional public-URL retrieval (SSRF-guarded, explicit click).

## Layout

- `app.py` — Streamlit UI (3 modes)
- `pruvcore/` — schemas + mock assessment pipeline
- `pruvfetch/` — file uploads + safe URL ingest (offline stub)
- `pruvcards/` — card rendering (dict/markdown)
- `providers/` — mock Meta provider (deterministic, offline)
- `fixtures/` — 3 small synthetic labeled fixtures
- `tests/` — pytest suite

See `ARCHITECTURE.md`, `DEMO.md`, `PREEXISTING.md`.

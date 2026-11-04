# PruvChat

Meta AI-powered multipurpose evidence assessment and verification platform.

PruvChat checks claims against evidence you supply. Every finding cites exact
sources, names its method, and states uncertainty and next action. Mock runs
offline for free. Live runs use the paid Meta Muse API with explicit
confirmation.

## Modes

- **Requirements** — Paste requirements, one per line. Add pasted evidence,
  uploaded files (TXT, MD, PDF, DOCX), or one fetched public page. Each
  requirement gets a check card with quotes and locators.
- **Business disputes** — Paste one claim plus Side A and Side B evidence.
  The same claim is scored against each side, with contradiction flags when
  evidence disagrees. Each side saves as its own workspace.
- **Custom review** — Free-form objective, claims, and evidence, plus optional
  public-URL retrieval (SSRF-guarded, explicit Fetch click only).
- **Visa review** — Four steps: destination, route, documents, results.
  Fetch one official immigration page (allowlisted domains, robots check,
  rate limit), confirm verbatim candidate lines, paste your checklist and
  evidence, then review coverage: Ready for review, Needs attention, or
  Missing evidence. Refresh re-checks the source without overwriting items.

All modes ship with synthetic Try example fixtures, clearly labeled as
fictional demo data.

## Mock versus Live Meta Muse AI

**Mock (offline, free)** is the default and needs no key.

- Deterministic keyword-overlap heuristic, no network, no randomness.
- Score is shared key words over claim key words. Verdicts: Supported
  (0.5 and above), Contested or Needs review (0.2 to 0.5), Unsupported
  or Missing (below 0.2).
- Every card carries `Method: keyword-overlap heuristic (not an AI judgment)`.
- Contradiction flags are heuristic leads for human review, not accusations.

**Live Meta API (billed)** calls Meta Muse models over HTTPS.

- Default model `muse-spark-1.3`, endpoint `https://api.meta.ai/v1`.
  Also known: `muse-spark-1.3-contributor`, `muse-spark-1.1`,
  `muse-wonder-1.0`.
- One grounded call per claim. The model receives numbered evidence and must
  cite by `[index]` only. Citations are validated against evidence the model
  actually received. Unknown, out-of-range, or missing citations never become
  verdicts.
- Support with zero citations is downgraded to UNVERIFIED. Failed, refused,
  truncated, or unparseable calls record explicit UNVERIFIED findings with a
  `live fallback` method. Failures never show mock results and never drop
  claims silently.
- Spend controls: 1024 max output tokens, minimal reasoning, 6000-char
  prompts, at most 12 evidence items per call (800 chars each, 1000 chars
  per claim), per-run call budget equal to claim count, zero retries,
  30 second timeout. Per-run tokens and rough USD estimate are shown, plus
  a per-session total in Settings.

## How Meta Muse AI is integrated

Live inference lives in `providers/meta_live.py` behind the `Provider`
protocol in `providers/base.py`. `providers/__init__.py` selects mock or
live and fails closed on unknown modes.

- Transport: OpenAI-compatible Chat Completions
  (`POST {base}/chat/completions`), Bearer `MODEL_API_KEY`, temperature 0,
  `response_format: json_schema` with strict schemas (`assessment` for
  simple prompts, `grounded_assessment` with verdict, rationale, and cited
  indexes for claim checks).
- Credentials come only from `<project>/.env` merged under the real
  environment (`MODEL_API_KEY` or `META_API_KEY`, plus optional
  `META_API_BASE` and `META_MODEL`). `.env` is git-ignored and never
  displayed. The UI shows only configured or missing, plus the endpoint host.
- Grounding: `select_grounding_evidence` ranks evidence by keyword relevance,
  fits whole items within budget, numbers them `[0]` to `[N]`, and maps
  returned positions back to original indexes. Sent, omitted, and shortened
  counts are disclosed on the card method and in run captions.
- Confirmation: switching the sidebar engine to Live only stages work.
  Each run shows its billable call count and needs a second explicit
  `Confirm & run live (spend credits)` click. Cancel discards the staged job.
  Nothing is billed before that click.
- Observability: token usage per run, rough cost from docs prices, and
  metadata-only diagnostics (HTTP status, error type, finish reason, token
  counts). No keys, headers, or response content are logged.
- Smoke check: `scripts/smoke_live.py` makes exactly one tiny call with a
  hardcoded budget of 1. Do not run it without explicit approval.

Promo API credits never cover Muse Code subscription charges.

## Evidence-grounded findings

Findings render as PruvCards (`pruvcards/render.py`).

- Title, plain status (Supported, Needs review, Missing), one plain sentence,
  and a next action.
- Exact excerpt per citation plus source and locator (`pasted text #N`,
  `upload:name`, `url:final-url`, official source links).
- Method line on every card, uncertainty (Low, Medium, High), and
  contradiction flags when other evidence disagrees.
- Live cards state `live Meta API (model), no overlap score` plus grounding
  notes. Fallback cards state UNVERIFIED and why.

## Saved workspaces and Markdown exports

- Save workspaces locally as JSON under `.pruvchat_runs/` (git-ignored,
  stays on this machine). Save, list, open, delete, and search from the
  sidebar. Runs are pruned to the newest 20, capped at 1 MB, truncated to
  2000 chars per text field, with secret-like keys redacted.
- Reopening restores inputs and rendered findings with a provenance banner
  (`Restored saved findings`, assessed time, engine, provider, model).
  No providers are called on open. Legacy inputs-only files restore inputs
  with a notice to rerun.
- Exports: `Download findings (.md)` for the current run and
  `Download full report (.md)` with header (mode, engine, run provenance),
  summary counts, and per-card method, uncertainty, excerpts, locators,
  flags, and next actions. Visa reports also include checklist source,
  official source lines, coverage rollup, and the safety note.
- Your optional display name is session-only. It is never saved or sent.

## Setup

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. Mock is selected by default.

For live Meta runs:

1. Copy `.env.example` to `.env` (git-ignored) and set `MODEL_API_KEY`.
2. Restart Streamlit, open Settings, switch the engine to
   **Live Meta API (billed)**.
3. Pick a model. Each run shows its call count and needs explicit confirm.

Run the offline suite (mocked HTTP, no live calls):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

## Prototype limitations

- Mock verdicts compare shared words, not truth. Weak matches are shown
  as-is with their overlap score. Always review the quoted sources.
- Scanned PDFs report no extractable text. OCR is not included.
- URL fetching opens public pages only (80/443, 500 KB and 10 s caps,
  3-redirect limit, DNS must resolve to public IPs). It cannot use logins,
  private drives, or unsupported content types.
- Visa preset addresses and portal links were not live verified in this
  sprint. Confirm each address opens the current official page before
  fetching. Only UK presets name specific visas. Other destinations use
  general categories or explicit manual paths, never invented route names.
- Visa candidate lines are verbatim excerpts tagged by wording cues only.
  Every candidate needs human review. Readiness is not approval and never
  decides eligibility.
- Live calls review at most 12 ranked items per claim. Omitted and shortened
  items are disclosed. Cost is a rough estimate. Check your Meta bill.
- Runs are local only, with no accounts, no sharing, and no cloud backup.

## Layout

- `app.py` — Streamlit workspace (Overview plus 4 modes, engine toggle)
- `pruvcore/` — schemas, mock pipeline, store, visa, navigation, viewstate
- `pruvfetch/` — uploads (TXT/MD/PDF/DOCX), guarded URL fetch, official sources
- `pruvcards/` — card dicts, Markdown, summaries
- `providers/` — mock provider (offline) plus live Meta client (approval-gated)
- `ui/` — white theme CSS
- `fixtures/` — 5 small synthetic labeled fixtures
- `scripts/smoke_live.py` — one-call live smoke test (approval only)
- `tests/` — pytest suite (mocked HTTP, no live calls)

See `ARCHITECTURE.md`, `DEMO.md`, `PREEXISTING.md`, `WRITING_STYLE.md`.

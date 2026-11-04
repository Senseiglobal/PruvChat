# PruvChat Architecture (Mock plus Live Meta)

Mock heuristic core with live Meta Muse calls behind explicit confirmation.
Ingestion boundaries are real: uploads (including PDF and DOCX), opt-in
public-URL retrieval with SSRF guards, official immigration page fetches,
and local run persistence. Mock needs no key. Live needs a key and a second
confirm per run.

## Components

- `pruvcore/schemas.py` — frozen dataclasses: `Document`, `Claim`,
  `EvidenceRef`, `Assessment`, plus `Verdict` enum (supported, contested,
  unsupported) and `Mode` enum (requirements, disputes, custom).
- `pruvcore/pipeline.py` — deterministic mock pipeline plus shared helpers:
  1. `extract_claims` splits text into sentence-level claims (rule-based).
  2. `score_claim` keyword-overlaps each claim against supplied evidence.
  3. `assess` maps score to verdict plus rationale.
  4. `rank_by_overlap`, `find_contradictions`, `annotate_contradictions`,
     `uncertainty_for`, and `fallback_unverified` support grounding,
     flags, and live fallbacks.
- `pruvcore/visa.py` — coverage labels (Ready for review, Needs attention,
  Missing evidence), rollups, and the safety note. Pure functions.
- `pruvcore/navigation.py`, `pruvcore/viewstate.py` — staged page nav and
  engine-gated result stash so Save and downloads survive reruns.
- `pruvcore/countries.py` — destination list plus quick picks. Spot-checked,
  not ISO verified.
- `pruvcore/store.py` — local run workspaces as JSON under
  `.pruvchat_runs/` (git-ignored): save, list, load, delete, restore,
  export, secret scrubbing, truncation, 1 MB cap, 20-run pruning.
- `pruvfetch/uploads.py` plus `extract.py` — reads `.txt`, `.md`, `.pdf`,
  `.docx` bytes with size and count caps. PDF and DOCX parse failures and
  scanned PDFs yield warnings, never fake text. Pure functions, no disk
  writes.
- `pruvfetch/urls.py` — URL validation (scheme, host blocklist,
  credentialed URLs). No network I/O.
- `pruvfetch/fetch.py` — opt-in public-URL retrieval: per-hop
  re-validation, DNS must resolve to public IPs, 80 and 443 only,
  3-redirect cap, 500 KB and 10 s caps, HTML text extraction, title and
  date meta, provenance (final URL, status, timestamp) on every fetch.
- `pruvfetch/official.py` — single official page fetches for visa reviews:
  allowlisted gov domains, robots check, 10 s rate limit, verbatim
  candidate extraction with wording hints, content hashing for refresh
  comparison, pack and unpack for saved runs. Applicant documents never
  leave the machine.
- `pruvcards/render.py` — renders an `Assessment` to card dicts, Markdown,
  plain verdicts, blockquotes, and summaries for Streamlit.
- `providers/meta_mock.py` — `MockMetaProvider` implementing
  `providers/base.py` `Provider` protocol. Deterministic canned verdicts
  from prompt keywords. Records calls for tests.
- `providers/meta_live.py` — live Meta Model API client
  (OpenAI-compatible `https://api.meta.ai/v1`, Bearer `MODEL_API_KEY`,
  `muse-spark` models). Grounded `assess_claim` with strict JSON schema,
  citation validation, context budgeting, call budgets, usage and cost
  tracking, metadata-only diagnostics. Zero retries. No calls without
  explicit user approval.
- `providers/__init__.py` — `get_provider` for mock or live. Fails closed
  on unknown modes. Live loads `.env` merged under the environment.
- `app.py` — Streamlit workspace: Overview plus 4 modes, staged progress,
  live confirm gate, save and export, sidebar workspaces. Never logs
  secrets. Shows `MOCK MODE` or `LIVE MODE` banners.
- `ui/theme.py` — single white theme CSS, no JavaScript.
- `scripts/smoke_live.py` — one-call live smoke test, budget hardcoded
  to 1. Approval only.

## Data flow

```text
UI input (text, upload, URL, official source) -> claims plus evidence
  -> mock assess OR live assess_claim per claim (confirmed)
  -> Assessment -> pruvcards -> Streamlit cards, saved JSON, Markdown export
```

## Trust boundaries

- Mock verdicts are heuristics. Live verdicts are grounded model outputs
  with checked citations. Failures in live become UNVERIFIED fallbacks,
  never mock verdicts.
- Fetches are user-triggered only. Each hop is re-validated. Official
  fetches add allowlist, robots, and rate limits.
- Saved runs stay local. Secrets stay in `.env` and are never displayed,
  saved, or logged.

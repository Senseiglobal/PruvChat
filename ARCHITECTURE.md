# PruvChat Architecture (Phase 2, Mock Verdicts)

Mock verdict core with real ingestion boundaries: uploads (incl. PDF/DOCX),
opt-in public-URL retrieval with SSRF guards, and local run persistence.
Assessment verdicts stay offline heuristics; live Meta calls need approval.

## Components

- `pruvcore/schemas.py` — frozen dataclasses: `Document`, `Claim`, `EvidenceRef`,
  `Assessment`, plus `Verdict` enum (`supported` / `contested` / `unsupported`) and
  `Mode` enum (requirements / disputes / custom).
- `pruvcore/pipeline.py` — deterministic mock pipeline:
  1. `extract_claims` splits text into sentence-level claims (rule-based).
  2. `score_claim` keyword-overlaps each claim against supplied evidence strings.
  3. `assess` maps score to verdict + rationale; returns `Assessment`.
- `pruvfetch/uploads.py` + `extract.py` — reads `.txt`/`.md`/`.pdf`/`.docx` bytes
  with size/count caps; PDF/DOCX parse failures and scanned PDFs yield warnings,
  never fake text. Pure functions, no disk writes.
- `pruvfetch/urls.py` — URL validation (scheme, host blocklist, credentialed URLs).
- `pruvfetch/fetch.py` — opt-in public-URL retrieval: per-hop re-validation, DNS
  must resolve to public IPs, 80/443 only, 3-redirect cap, 500KB/10s caps, HTML
  text extraction, provenance (final URL, status, timestamp) on every fetch.
- `pruvcore/store.py` — local run workspaces as JSON under `.pruvchat_runs/`
  (git-ignored): save/list/load/delete, secret scrubbing, 20-run pruning.
- `pruvcards/render.py` — renders an `Assessment` to card dicts, Markdown, and
  one-line summaries for Streamlit.
- `providers/meta_mock.py` — `MockMetaProvider` implementing `providers/base.py`
  `Provider` protocol. Deterministic canned verdicts from prompt keywords; records
  calls for tests. Live client now in `providers/meta_live.py` (verified, approval-gated).
  (OpenAI-compatible `https://api.meta.ai/v1`, Bearer key, `muse-spark-*` models).
- `app.py` — Streamlit workspace: dashboard, 3 modes, staged progress, save/export. Never logs secrets; shows
  `MOCK MODE` banner.

## Data flow

```text
UI input (text / upload / URL stub) -> Document -> pipeline.assess -> Assessment -> pruvcards -> Streamlit
```

## Phase 2 seams (not built)

- Real provider: implement `Provider.generate()` against Meta Model API with
  `response_format: json_schema` constrained decoding.
- Real URL fetch: allowlist + SSRF guards + timeouts, behind explicit opt-in flag.

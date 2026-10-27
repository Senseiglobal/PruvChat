# PruvChat pre-existing work disclosure (Phase 1)

Date: 2026-10-27. Status: no pre-existing PruvChat code existed at scaffold time.

## Observed starting state

- `C:\Users\User\PruvChat` contained zero files and five directories only:
  `.agents`, `.eden`, `.hg`, `.muse`, `.sl` (verified via `Get-ChildItem -Force`).
- No `.git` at top level: `git status`, `git log`, `git remote -v` all returned
  `fatal: not a git repository`.
- No application source, fixtures, tests, or docs existed before this build.

## What this build adds

All files in this MVP (`app.py`, `pruvcore/`, `pruvfetch/`, `pruvcards/`,
`providers/`, `fixtures/`, `tests/`, docs, configs) were authored fresh in this
session as original hackathon work. No code was copied from another product.

## Third-party components

- Only third-party packages are declared open-source deps in `requirements.txt`
  (Streamlit, pytest) under their own licenses.
- No EvidenceDesk code was touched, read, or reused (explicit boundary).

## Gaps (from discovery)

- Official Rules / waiver full text not directly inspected (JS-gated portal);
  built-during-window and AI-assisted-dev clauses unverified. If the published
  Official Rules require a narrower disclosure format, update this file to match.

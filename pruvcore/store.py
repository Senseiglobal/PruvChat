"""Local workspace persistence. JSON files in a project-local runs directory.

Privacy: stores only assessment inputs/results (truncated), never credentials.
Directory is git-ignored; runs never leave the machine unless exported.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import re as _re

from pruvcore.schemas import Assessment, Claim, EvidenceRef, Verdict

RUNS_DIRNAME = ".pruvchat_runs"
MAX_RUNS = 20
MAX_RUN_BYTES = 1_000_000
MAX_TEXT_CHARS = 2000
_SECRET_HINTS = ("key", "token", "secret", "password", "credential", "auth")


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def sanitize_name(name: str) -> str:
    """Allow letters, digits, dash, underscore; anything else becomes '-'."""
    clean = _re.sub(r"[^A-Za-z0-9_-]+", "-", (name or "").strip()).strip("-")[:60]
    return clean or "run"


def _scrub(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(h in str(k).lower() for h in _SECRET_HINTS) else _scrub(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
        return value[:MAX_TEXT_CHARS] + "…[truncated]"
    return value


def _runs_dir(directory: str) -> str:
    path = _os.path.join(directory, RUNS_DIRNAME)
    _os.makedirs(path, exist_ok=True)
    return path


def _prune(runs_dir: str) -> None:
    try:
        files = sorted((_os.path.join(runs_dir, f) for f in _os.listdir(runs_dir)
                        if f.endswith(".json")), key=_os.path.getmtime)
    except OSError:
        return
    for stale in files[: max(0, len(files) - MAX_RUNS)]:
        try:
            _os.remove(stale)
        except OSError:
            pass


def save_run(directory: str, name: str, mode: str, inputs: dict,
             cards: list, summary: dict, engine: str = "mock",
             provider: str = "mock", model: str = "") -> str:
    """Save one assessment run; returns the file path. Raises on oversize."""
    runs_dir = _runs_dir(directory)
    payload = {"saved_at": _stamp(), "name": sanitize_name(name) or "run", "mode": mode,
               "engine": str(engine or "mock"), "provider": str(provider or "mock"),
               "model": str(model or ""),
               "inputs": _scrub(dict(inputs or {})), "cards": _scrub(list(cards or [])),
               "summary": _scrub(dict(summary or {}))}
    raw = _json.dumps(payload, ensure_ascii=False, indent=1)
    if len(raw.encode("utf-8")) > MAX_RUN_BYTES:
        raise ValueError("run too large to save (>1MB)")
    fname = f"{payload['saved_at'].replace(':', '-').replace('+', 'z')}_{payload['name']}.json"
    path = _os.path.join(runs_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(raw)
    _prune(runs_dir)
    return path


def list_runs(directory: str) -> list:
    """Newest-first run summaries; skips unreadable files."""
    runs_dir = _os.path.join(directory, RUNS_DIRNAME)
    try:
        names = [f for f in _os.listdir(runs_dir) if f.endswith(".json")]
    except OSError:
        return []
    runs = []
    for fname in names:
        try:
            with open(_os.path.join(runs_dir, fname), encoding="utf-8") as fh:
                data = _json.load(fh)
            runs.append({"file": fname, "name": data.get("name", "?"),
                         "mode": data.get("mode", "?"), "saved_at": data.get("saved_at", "?"),
                         "total": (data.get("summary") or {}).get("total", 0)})
        except (OSError, ValueError):
            continue
    return sorted(runs, key=lambda r: r["saved_at"], reverse=True)


def load_run(directory: str, fname: str) -> dict:
    """Load one run by file name. Raises FileNotFoundError/ValueError."""
    if _os.path.basename(fname) != fname or not fname.endswith(".json"):
        raise ValueError("invalid run file name")
    path = _os.path.join(directory, RUNS_DIRNAME, fname)
    if not _os.path.isfile(path):
        raise FileNotFoundError(f"no such run: {fname}")
    with open(path, encoding="utf-8") as fh:
        data = _json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("corrupt run file")
    if not isinstance(data.get("inputs"), dict):
        raise ValueError("corrupt run file: inputs missing")
    data.setdefault("cards", [])  # absent cards = legacy inputs-only file
    if not isinstance(data["cards"], list):
        raise ValueError("corrupt run file: cards malformed")
    return data


def restore_workspace(data: dict) -> dict:
    """Validate saved JSON and rebuild render-ready objects. Never fabricates.

    Returns {"mode", "inputs", "assessments", "evidence", "engine", "provider",
    "model", "saved_at", "legacy"}. Files without cards restore inputs-only
    (legacy=True). Anything malformed raises ValueError for graceful handling.
    """
    if not isinstance(data, dict) or not isinstance(data.get("inputs"), dict):
        raise ValueError("corrupt run file: inputs missing")
    inputs = data["inputs"]
    for key, val in inputs.items():
        if not isinstance(val, str):
            raise ValueError(f"corrupt run file: inputs[{key!r}] is not text")
    base = {"mode": data.get("mode", "?"), "inputs": dict(inputs),
            "engine": str(data.get("engine") or "mock"),
            "provider": str(data.get("provider") or "mock"),
            "model": str(data.get("model") or ""),
            "saved_at": str(data.get("saved_at") or "?")}
    cards = data.get("cards") or []
    if not cards:
        return {**base, "assessments": [], "evidence": [], "legacy": True}
    assessments: list = []
    evidence: list = []
    seen_evidence: set = set()
    for pos, card in enumerate(cards):
        assessments.append(_restore_assessment(card, pos))
        for cite in card["citations"]:
            if cite["id"] not in seen_evidence:
                seen_evidence.add(cite["id"])
                evidence.append(EvidenceRef(id=cite["id"], text=cite.get("excerpt", ""),
                                            source=cite.get("source", "") or "saved",
                                            locator=cite.get("locator", "") or ""))
    return {**base, "assessments": assessments, "evidence": evidence, "legacy": False}


def _restore_assessment(card: dict, pos: int):
    """Rebuild one Assessment from a saved card dict. Strict, no invention."""
    if not isinstance(card, dict):
        raise ValueError(f"corrupt run file: card {pos} is not an object")
    for field in ("claim", "claim_id", "status", "rationale"):
        if not isinstance(card.get(field), str):
            raise ValueError(f"corrupt run file: card {pos} field {field!r} invalid")
    try:
        verdict = Verdict(card["status"])
    except ValueError:
        raise ValueError(f"corrupt run file: card {pos} has unknown status") from None
    score = card.get("score", 0)
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(f"corrupt run file: card {pos} score invalid")
    for field in ("evidence_ids", "citations", "contradicted_by"):
        if not isinstance(card.get(field), list):
            raise ValueError(f"corrupt run file: card {pos} field {field!r} invalid")
    for cite in card["citations"]:
        if not isinstance(cite, dict) or not isinstance(cite.get("id"), str):
            raise ValueError(f"corrupt run file: card {pos} has a bad citation")
        for key in ("source", "locator", "excerpt"):
            if not isinstance(cite.get(key, ""), str):
                raise ValueError(f"corrupt run file: card {pos} citation {key!r} invalid")
    uncertainty = str(card.get("uncertainty", "medium")).lower()
    if uncertainty not in ("low", "medium", "high"):
        raise ValueError(f"corrupt run file: card {pos} uncertainty invalid")
    return Assessment(claim=Claim(id=card["claim_id"], text=card["claim"]),
                      verdict=verdict, score=float(score), rationale=card["rationale"],
                      evidence_ids=tuple(e for e in card["evidence_ids"] if isinstance(e, str)),
                      uncertainty=uncertainty,
                      contradicted_by=tuple(e for e in card["contradicted_by"] if isinstance(e, str)),
                      method=str(card.get("method", "")))


def delete_run(directory: str, fname: str) -> bool:
    """Delete one run; returns True if a file was removed."""
    if _os.path.basename(fname) != fname or not fname.endswith(".json"):
        return False
    path = _os.path.join(directory, RUNS_DIRNAME, fname)
    try:
        _os.remove(path)
        return True
    except OSError:
        return False


def export_report(data: dict) -> str:
    """Render a saved run as a Markdown report."""
    lines = [f"# PruvChat report: {data.get('name', '?')}",
             f"- Mode: {data.get('mode', '?')}  |  Saved: {data.get('saved_at', '?')}",
             f"- Engine: {data.get('engine', 'mock')}  |  Provider: {data.get('provider', 'mock')}"
             + (f" ({data.get('model')})" if data.get("model") else ""),
             ""]
    summary = data.get("summary") or {}
    lines.append(f"Summary: {summary.get('supported', 0)} supported / "
                 f"{summary.get('contested', 0)} contested / "
                 f"{summary.get('unsupported', 0)} unproven "
                 f"({summary.get('total', 0)} total)")
    lines.append("")
    for card in data.get("cards") or []:
        method = str(card.get("method") or "")
        if method.startswith("live fallback"):
            basis = "live fallback, UNVERIFIED, not a verdict"
        elif method.startswith("live"):
            basis = "live Meta API verdict, no overlap score"
        else:
            basis = f"heuristic overlap {card.get('score', '?')}"
        lines.append(f"## {card.get('title', '?')}")
        lines.append(f"- Status: **{card.get('status', '?')}** ({basis})")
        lines.append(f"- Method: {card.get('method', 'mock heuristic')}")
        lines.append(f"- Claim: {card.get('claim', '?')}")
        lines.append(f"- Rationale: {card.get('rationale', '?')}")
        cites = card.get("citations") or []
        if cites:
            lines.append("- Evidence:")
            for c in cites:
                ref = f"{c.get('id', '?')} [{c.get('locator', '')}]" if c.get("locator") else c.get("id", "?")
                lines.append(f"  - {ref}: \"{c.get('excerpt', '')}\"")
        else:
            lines.append("- Evidence: none")
        if card.get("contradicted_by"):
            lines.append(f"- Contradiction flags: {', '.join(card['contradicted_by'])}")
        lines.append(f"- Uncertainty: {card.get('uncertainty', '?')}")
        lines.append(f"- Next action: {card.get('next_action', '?')}")
        lines.append("")
    return "\n".join(lines).strip()

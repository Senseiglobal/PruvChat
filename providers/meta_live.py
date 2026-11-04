"""Live Meta Model API client. Real HTTPS, env-only credentials, no retries.

Verified against https://dev.meta.ai/docs (Oct 2026): base URL
https://api.meta.ai/v1, Bearer auth, OpenAI-compatible Chat Completions plus
a native Responses API. Make NO live calls without explicit user approval.
"""
from __future__ import annotations

import json as _json
import os as _os
import re as _re
from dataclasses import dataclass, field
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pruvcore.pipeline import rank_by_overlap

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"
KNOWN_MODELS = ("muse-spark-1.3", "muse-spark-1.3-contributor", "muse-spark-1.1", "muse-wonder-1.0")
TIMEOUT = 30
# Output budget must cover invisible reasoning tokens (billed, counted toward
# max_tokens per docs) plus the visible JSON. 300 starved the model (observed
# finish_reason=length with null content); 1024 gives headroom at minimal effort.
MAX_OUTPUT_TOKENS = 1024
# Shortest reasoning pass ("none" returns HTTP 400 on Muse models per docs).
REASONING_EFFORT = "minimal"
MAX_PROMPT_CHARS = 6000
MAX_EVIDENCE_ITEMS = 12
MAX_ITEM_CHARS = 800
MAX_CLAIM_CHARS = 1000
_TRUNC_MARK = " […]"
_DECIDER = ("Decide: supported (some evidence directly backs the claim), "
            "contested (evidence disagrees or only partly backs it), or "
            "unsupported. Cite evidence by [index] only; cite nothing you were not given.")

# Per-1M-token prices from docs (input / cached / output); verify before billing use.
PRICES_PER_MTOK = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
}

_VERDICT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["supported", "contested", "unsupported"]},
                "rationale": {"type": "string"},
            },
            "required": ["verdict", "rationale"],
            "additionalProperties": False,
        },
    },
}

_GROUNDED_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "grounded_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["supported", "contested", "unsupported"]},
                "rationale": {"type": "string"},
                "cited": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["verdict", "rationale", "cited"],
            "additionalProperties": False,
        },
    },
}


class ConfigError(RuntimeError):
    pass


class ProviderError(RuntimeError):
    pass


def load_dotenv(path: str) -> dict:
    """Parse a KEY=VALUE dotenv file. Missing file -> {}. Never raises on content."""
    values: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"").strip()
        if key and val and key.replace("_", "").isalnum():
            values[key] = val
    return values


def _http_error(exc: HTTPError) -> tuple:
    """Map an HTTP failure to (ProviderError, diagnostics). Metadata only:
    status, envelope type/code, truncated reason. Never headers, keys, or
    response content."""
    code = getattr(exc, "code", 0) or 0
    try:
        raw_body = exc.read() or b""
    except Exception:
        raw_body = b""
    msg, etype, ecode = "", "", ""
    try:
        err = _json.loads(raw_body[:2000].decode("utf-8", errors="replace")).get("error") or {}
        msg = str(err.get("message", "") or "")[:200]
        etype = str(err.get("type", "") or "")[:60]
        ecode = str(err.get("code", "") or "")[:60]
    except (ValueError, AttributeError):
        pass
    diag = {"http_status": code, "error_type": etype or None, "error_code": ecode or None}
    bits = [msg] + ([f"(type={etype})"] if etype else []) + ([f"[code={ecode}]"] if ecode else [])
    detail = " ".join(b for b in bits if b).strip()
    suffix = f": {detail}" if detail else ""
    if code == 401:
        err = ProviderError(f"Meta API authentication failed (HTTP 401){suffix} "
                            "-- check MODEL_API_KEY (missing, invalid, or revoked)")
    elif code == 402:
        err = ProviderError(f"Meta API billing restriction (HTTP 402){suffix} "
                            "-- check credits and payment method on the dashboard")
    elif code == 403:
        err = ProviderError(f"Meta API permission denied (HTTP 403){suffix} "
                            "-- key lacks access to this model or feature")
    elif code == 404:
        err = ProviderError(f"Meta API not found (HTTP 404){suffix} "
                            "-- check endpoint path and model name")
    elif code == 429:
        err = ProviderError(f"Meta API rate limited (HTTP 429){suffix} "
                            "-- wait and retry manually (no automatic retries)")
    elif 500 <= code <= 599:
        err = ProviderError(f"Meta API server error (HTTP {code}){suffix} "
                            "-- retry manually later")
    else:
        err = ProviderError(f"Meta API error (HTTP {code}){suffix}")
    return err, diag


@dataclass(frozen=True)
class MetaConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls, env: dict | None = None) -> "MetaConfig":
        src = env if env is not None else _os.environ
        key = (src.get("MODEL_API_KEY") or src.get("META_API_KEY") or "").strip()
        if not key:
            raise ConfigError("Set MODEL_API_KEY (or META_API_KEY) in the environment; "
                              "never commit keys to git.")
        return cls(api_key=key,
                   base_url=(src.get("META_API_BASE") or DEFAULT_BASE_URL).rstrip("/"),
                   model=(src.get("META_MODEL") or DEFAULT_MODEL).strip())

    @staticmethod
    def has_key(env: dict | None = None) -> bool:
        """True when an API key is present. Never returns the key itself."""
        src = env if env is not None else _os.environ
        return bool((src.get("MODEL_API_KEY") or src.get("META_API_KEY") or "").strip())

    @classmethod
    def local(cls, project_dir: str, env: dict | None = None) -> "MetaConfig":
        """Config from <project_dir>/.env merged under the real environment."""
        merged = load_dotenv(_os.path.join(project_dir, ".env"))
        live = env if env is not None else dict(_os.environ)
        merged.update({k: v for k, v in live.items() if v})
        return cls.from_env(merged)


class MetaLiveProvider:
    """Drop-in Provider backed by the live Chat Completions endpoint."""

    def __init__(self, config: MetaConfig | None = None, call_budget: int | None = None):
        self.config = config or MetaConfig.from_env()
        self.call_budget = call_budget
        self.calls: list = []
        self.last_usage: dict = {"input_tokens": 0, "output_tokens": 0}
        self.usage_total = {"input_tokens": 0, "output_tokens": 0}
        self.last_diagnostics: dict = {}

    def _check_budget(self) -> None:
        if self.call_budget is not None and len(self.calls) >= self.call_budget:
            raise ProviderError(f"call budget exhausted ({self.call_budget} call(s) allowed)")

    @property
    def model(self) -> str:
        return self.config.model

    def _post(self, path: str, payload: dict) -> dict:
        data = _json.dumps(payload).encode("utf-8")
        req = Request(f"{self.config.base_url}{path}", data=data, method="POST",
                      headers={"Authorization": f"Bearer {self.config.api_key}",
                               "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=TIMEOUT) as resp:
                status = getattr(resp, "status", 200) or 200
                raw_bytes = resp.read()
        except HTTPError as exc:
            err, diag = _http_error(exc)
            self.last_diagnostics = diag
            raise err
        except Exception as exc:
            raise ProviderError(f"Meta API request failed: {type(exc).__name__}") from exc
        try:
            parsed = _json.loads(raw_bytes.decode("utf-8"))
        except ValueError:
            raise ProviderError(f"Meta API returned non-JSON body (HTTP {status})") from None
        if not isinstance(parsed, dict):
            raise ProviderError(f"Meta API returned non-object JSON (HTTP {status})")
        return parsed

    def _extract_text_and_usage(self, raw: dict) -> tuple:
        """Pull (text, usage) from a chat-completion object with precise errors.

        Accepts content as a string or a list of text blocks, and usage in
        OpenAI (prompt/completion) or Anthropic (input/output) naming. Records
        safe structural diagnostics (keys, finish_reason, refusal presence,
        token counts. Never content or secrets) on last_diagnostics and in
        error messages. Null content with a refusal raises a refusal error;
        bare null content raises with structural clues. Neither invents text.
        """
        top_keys = sorted(raw.keys()) if isinstance(raw, dict) else []
        try:
            choice = raw["choices"][0]
        except (KeyError, IndexError, TypeError):
            self.last_diagnostics = {"http_status": 200, "top_keys": top_keys,
                                     "finish_reason": None, "refusal_present": False}
            raise ProviderError("unexpected shape: missing choices[0]") from None
        if not isinstance(choice, dict):
            self.last_diagnostics = {"http_status": 200, "top_keys": top_keys,
                                     "finish_reason": None, "refusal_present": False}
            raise ProviderError("unexpected shape: choices[0] is not an object") from None
        finish = choice.get("finish_reason")
        message = choice.get("message", {})
        if not isinstance(message, dict):
            self.last_diagnostics = {"http_status": 200, "top_keys": top_keys,
                                     "choice_keys": sorted(choice.keys()),
                                     "finish_reason": finish, "refusal_present": False}
            raise ProviderError("unexpected shape: choices[0].message is not an object") from None
        usage = raw.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        inp, outp = self._usage_tokens(usage)
        diag = {"http_status": 200, "top_keys": top_keys,
                "choice_keys": sorted(choice.keys()), "message_keys": sorted(message.keys()),
                "finish_reason": finish, "usage": {"input_tokens": inp, "output_tokens": outp}}
        if isinstance(usage.get("reasoning_tokens"), int):
            diag["reasoning_tokens"] = usage["reasoning_tokens"]
        content = message.get("content")
        if content is None:
            refusal = message.get("refusal")
            reason = refusal[:200] if isinstance(refusal, str) and refusal else ""
            diag["refusal_present"] = bool(reason)
            diag["refusal_len"] = len(refusal) if isinstance(refusal, str) else 0
            self.last_diagnostics = diag
            if reason:
                raise ProviderError(f"refused by model (finish_reason={finish!r}; "
                                    f"reason {len(refusal)} chars, truncated): {reason!r} "
                                    "-- no verdict recorded") from None
            if finish == "length":
                raise ProviderError(f"truncated by output-token budget (finish_reason='length'; "
                                    f"{outp} output tokens used of {MAX_OUTPUT_TOKENS} cap) "
                                    "-- raise budget or lower reasoning effort; "
                                    "no verdict recorded") from None
            raise ProviderError(f"unexpected shape: message.content is null "
                                f"(finish_reason={finish!r}; message keys={diag['message_keys']}; "
                                f"usage={diag['usage']}). No verdict recorded") from None
        diag["refusal_present"] = False
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and isinstance(b.get("text"), str)]
            text = "".join(parts)
            if not text:
                diag["content_blocks"] = len(content)
                self.last_diagnostics = diag
                raise ProviderError("unexpected shape: content blocks carry no text") from None
        else:
            diag["content_type"] = type(content).__name__
            self.last_diagnostics = diag
            raise ProviderError(f"unexpected shape: content has type "
                                f"{type(content).__name__}, expected str or blocks") from None
        diag["content_chars"] = len(text)
        self.last_diagnostics = diag
        return text, usage

    @staticmethod
    def _usage_tokens(usage: dict) -> tuple:
        """(input, output) ints from either usage naming convention."""
        try:
            inp = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
            out = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            return int(inp), int(out)
        except (TypeError, ValueError):
            return 0, 0

    def generate(self, prompt: str) -> dict:
        """Assess one prompt; returns verdict/rationale/model. Single attempt."""
        text = (prompt or "").strip()
        if not text:
            return {"verdict": "unsupported", "rationale": "Empty prompt; nothing to assess.",
                    "model": self.model}
        self._check_budget()
        body = {"model": self.model,
                "messages": [{"role": "system", "content": "You assess whether evidence supports a claim. "
                              "Reply only with the requested JSON."},
                             {"role": "user", "content": text}],
                "temperature": 0,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "reasoning_effort": REASONING_EFFORT,
                "response_format": _VERDICT_SCHEMA}
        raw = self._post("/chat/completions", body)
        content, usage = self._extract_text_and_usage(raw)
        self.calls.append(text)
        inp, outp = self._usage_tokens(usage)
        self.last_usage = {"input_tokens": inp, "output_tokens": outp}
        self.usage_total["input_tokens"] += self.last_usage["input_tokens"]
        self.usage_total["output_tokens"] += self.last_usage["output_tokens"]
        try:
            parsed = _json.loads(content)
            verdict = parsed["verdict"]
            rationale = parsed.get("rationale", "")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Meta API returned unparseable JSON") from exc
        if verdict not in ("supported", "contested", "unsupported"):
            raise ProviderError("Meta API returned an unknown verdict")
        return {"verdict": verdict, "rationale": str(rationale), "model": self.model}

    @staticmethod
    def _shorten_item(text: str, cap: int = MAX_ITEM_CHARS) -> tuple:
        """Cut an over-long item at a sentence/word boundary with a marker.

        Returns (text, was_shortened). The marker tells the model the excerpt
        is partial, so a cut mid-document cannot read as a complete statement.
        Pure function.
        """
        clean = (text or "").strip()
        if len(clean) <= cap:
            return clean, False
        head = clean[: cap - len(_TRUNC_MARK)]
        end = -1
        for match in _re.finditer(r"[.!?](?=\s|$)", head):
            end = match.end()
        if end > 0:
            short = head[:end]
        elif " " in head:
            short = head[: head.rfind(" ")]
        else:
            short = head
        return short.rstrip() + _TRUNC_MARK, True

    @staticmethod
    def select_grounding_evidence(claim: str, evidence: list,
                                  max_items: int = MAX_EVIDENCE_ITEMS,
                                  max_chars: int = MAX_PROMPT_CHARS) -> dict:
        """Rank, cap, and number evidence for one grounded call. Pure function.

        Items are ranked by keyword relevance to the claim (ties keep original
        order) and added while each fits whole within the char budget, up to
        max_items. Returns {"prompt", "sent", "omitted", "shortened"} where
        sent[i] is the ORIGINAL index of numbered item [i], so citations can
        only resolve to evidence the model actually received.
        """
        texts = [str(e).strip() for e in (evidence or [])]
        usable = [i for i, text in enumerate(texts) if text]
        usable_set = set(usable)
        ranked = [i for i in rank_by_overlap(claim or "", texts) if i in usable_set]
        header = f"Claim: {(claim or '').strip()[:MAX_CLAIM_CHARS]}\nEvidence:\n"
        footer = "\n" + _DECIDER
        budget = max_chars - len(header) - len(footer)
        lines: list = []
        sent: list = []
        shortened = 0
        used = 0
        for orig in ranked:
            if len(lines) >= max_items:
                break
            short, was_cut = MetaLiveProvider._shorten_item(texts[orig])
            line = f"[{len(lines)}] {short}"
            need = len(line) + (1 if lines else 0)
            if used + need > budget:
                break  # first non-fitting item stops: top-ranked stay contiguous
            lines.append(line)
            used += need
            sent.append(orig)
            shortened += 1 if was_cut else 0
        sent_set = set(sent)
        omitted = tuple(i for i in usable if i not in sent_set)
        return {"prompt": header + "\n".join(lines) + footer, "sent": tuple(sent),
                "omitted": omitted, "shortened": shortened}

    @staticmethod
    def build_grounded_prompt(claim: str, evidence: list) -> str:
        """Number the evidence and ask for index-only citations. Pure function."""
        return MetaLiveProvider.select_grounding_evidence(claim, evidence)["prompt"]

    @staticmethod
    def validate_citations(cited, n_evidence: int) -> tuple:
        """Strict check: ints in [0, n). Raises ProviderError. Never invent refs."""
        if not isinstance(cited, list):
            raise ProviderError("Meta API returned malformed citations")
        clean: list = []
        for c in cited:
            if isinstance(c, bool) or not isinstance(c, int) or not 0 <= c < n_evidence:
                raise ProviderError(f"Meta API cited out-of-range evidence [{c}]")
            if c not in clean:
                clean.append(c)
        return tuple(clean)

    def assess_claim(self, claim: str, evidence: list) -> dict:
        """One grounded billable call. Returns verdict/rationale/cited/model/usage.

        cited holds ORIGINAL indexes into `evidence`, mapped through the ranked
        selection actually sent; sent/omitted/shortened describe that selection
        so callers can disclose what the model did and did not review.
        """
        if not (claim or "").strip() or not evidence:
            raise ProviderError("assess_claim needs a claim and at least one evidence item")
        self._check_budget()
        selection = self.select_grounding_evidence(claim, evidence)
        if not selection["sent"]:
            raise ProviderError("assess_claim needs at least one non-empty evidence item")
        body = {"model": self.model,
                "messages": [{"role": "system", "content": "You are a strict evidence checker. "
                              "Use only the numbered evidence supplied. Reply only with JSON."},
                             {"role": "user", "content": selection["prompt"]}],
                "temperature": 0,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "reasoning_effort": REASONING_EFFORT,
                "response_format": _GROUNDED_SCHEMA}
        raw = self._post("/chat/completions", body)
        content, usage = self._extract_text_and_usage(raw)
        try:
            parsed = _json.loads(content)
        except ValueError:
            raise ProviderError("Meta API returned unparseable JSON content "
                                "(expected grounded_assessment JSON)") from None
        if not isinstance(parsed, dict):
            raise ProviderError("Meta API returned non-object JSON content") from None
        try:
            verdict = parsed["verdict"]
        except KeyError:
            raise ProviderError("Meta API JSON verdict missing") from None
        rationale = str(parsed.get("rationale", ""))
        positions = self.validate_citations(parsed.get("cited"), len(selection["sent"]))
        cited = tuple(selection["sent"][pos] for pos in positions)
        if verdict not in ("supported", "contested", "unsupported"):
            raise ProviderError("Meta API returned an unknown verdict")
        self.calls.append(selection["prompt"])
        inp, outp = self._usage_tokens(usage)
        self.last_usage = {"input_tokens": inp, "output_tokens": outp}
        self.usage_total["input_tokens"] += self.last_usage["input_tokens"]
        self.usage_total["output_tokens"] += self.last_usage["output_tokens"]
        return {"verdict": verdict, "rationale": rationale, "cited": cited,
                "model": self.model, "usage": dict(self.last_usage),
                "sent": selection["sent"], "omitted": selection["omitted"],
                "shortened": selection["shortened"]}

    def estimated_cost_usd(self) -> float:
        """Session spend estimate from tracked usage and docs prices."""
        prices = PRICES_PER_MTOK.get(self.model)
        if not prices:
            return 0.0
        inp, _, outp = prices
        return round(self.usage_total["input_tokens"] / 1e6 * inp
                     + self.usage_total["output_tokens"] / 1e6 * outp, 6)

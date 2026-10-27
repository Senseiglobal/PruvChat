"""Live Meta Model API client. Real HTTPS, env-only credentials, no retries.

Verified against https://dev.meta.ai/docs (Oct 2026): base URL
https://api.meta.ai/v1, Bearer auth, OpenAI-compatible Chat Completions plus
a native Responses API. Make NO live calls without explicit user approval.
"""
from __future__ import annotations

import json as _json
import os as _os
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"
TIMEOUT = 30
MAX_OUTPUT_TOKENS = 300

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


class ConfigError(RuntimeError):
    pass


class ProviderError(RuntimeError):
    pass


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


class MetaLiveProvider:
    """Drop-in Provider backed by the live Chat Completions endpoint."""

    def __init__(self, config: MetaConfig | None = None):
        self.config = config or MetaConfig.from_env()
        self.calls: list = []
        self.usage_total = {"input_tokens": 0, "output_tokens": 0}

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
                return _json.loads(resp.read().decode("utf-8"))
        except ConfigError:
            raise
        except Exception as exc:
            raise ProviderError(f"Meta API request failed: {type(exc).__name__}") from exc

    def generate(self, prompt: str) -> dict:
        """Assess one prompt; returns verdict/rationale/model. Single attempt."""
        text = (prompt or "").strip()
        if not text:
            return {"verdict": "unsupported", "rationale": "Empty prompt; nothing to assess.",
                    "model": self.model}
        body = {"model": self.model,
                "messages": [{"role": "system", "content": "You assess whether evidence supports a claim. "
                              "Reply only with the requested JSON."},
                             {"role": "user", "content": text}],
                "temperature": 0,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "response_format": _VERDICT_SCHEMA}
        raw = self._post("/chat/completions", body)
        try:
            content = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Meta API returned an unexpected shape") from exc
        self.calls.append(text)
        self.usage_total["input_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        self.usage_total["output_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        try:
            parsed = _json.loads(content)
            verdict = parsed["verdict"]
            rationale = parsed.get("rationale", "")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Meta API returned unparseable JSON") from exc
        if verdict not in ("supported", "contested", "unsupported"):
            raise ProviderError("Meta API returned an unknown verdict")
        return {"verdict": verdict, "rationale": str(rationale), "model": self.model}

    def estimated_cost_usd(self) -> float:
        """Session spend estimate from tracked usage and docs prices."""
        prices = PRICES_PER_MTOK.get(self.model)
        if not prices:
            return 0.0
        inp, _, outp = prices
        return round(self.usage_total["input_tokens"] / 1e6 * inp
                     + self.usage_total["output_tokens"] / 1e6 * outp, 6)

"""Approved-only live smoke test: exactly ONE tiny Meta Model API call.

Usage (from the project root, after explicit approval):
    python scripts/smoke_live.py

Requires MODEL_API_KEY in the environment or .env (git-ignored, never printed).
Budget is hardcoded to 1 call; there are no retries. Prints the endpoint,
model, verdict, token usage, and docs-based cost estimate.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.meta_live import (
    MAX_OUTPUT_TOKENS,
    REASONING_EFFORT,
    ConfigError,
    MetaConfig,
    MetaLiveProvider,
    ProviderError,
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        provider = MetaLiveProvider(MetaConfig.local(PROJECT_DIR), call_budget=1)
    except ConfigError as exc:
        print(f"SMOKE ABORTED (config): {exc}")
        return 2
    print(f"endpoint: {provider.config.base_url}/chat/completions")
    print(f"model: {provider.model} | budget: 1 call | retries: 0 | "
          f"max_tokens: {MAX_OUTPUT_TOKENS} | reasoning_effort: {REASONING_EFFORT}")
    try:
        out = provider.assess_claim("The sky appears blue.", ["Sky appears blue at noon."])
    except ProviderError as exc:
        print(f"SMOKE FAILED (api): {exc}")
        print(f"diagnostics: {json.dumps(provider.last_diagnostics, sort_keys=True)}")
        return 1
    print(f"verdict: {out['verdict']}")
    print(f"rationale: {str(out['rationale'])[:200]}")
    print(f"usage: {out['usage']} | est. cost: ${provider.estimated_cost_usd():.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

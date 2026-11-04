"""Providers: mock (offline) default; live Meta client for approved calls."""
from __future__ import annotations

from dataclasses import replace

from providers.meta_live import DEFAULT_MODEL, KNOWN_MODELS, MetaConfig, MetaLiveProvider
from providers.meta_mock import MockMetaProvider

__all__ = ["DEFAULT_MODEL", "KNOWN_MODELS", "MetaConfig", "MetaLiveProvider",
           "MockMetaProvider", "get_provider"]


def get_provider(mode: str, project_dir: str = ".", model: str | None = None,
                 call_budget: int | None = None):
    """Return the provider for 'mock' or 'live'. Unknown modes raise (fail closed).

    Live loads credentials from <project_dir>/.env merged under the environment;
    missing keys raise ConfigError. Model defaults to the documented default.
    """
    if mode == "mock":
        return MockMetaProvider()
    if mode == "live":
        config = MetaConfig.local(project_dir)
        if model:
            config = replace(config, model=model.strip() or config.model)
        return MetaLiveProvider(config, call_budget=call_budget)
    raise ValueError(f"unknown provider mode: {mode!r} (expected 'mock' or 'live')")

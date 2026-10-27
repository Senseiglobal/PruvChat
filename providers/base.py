"""Provider protocol. Live Meta provider plugs in here in Phase 2."""
from __future__ import annotations

from typing import Protocol


class Provider(Protocol):
    def generate(self, prompt: str) -> dict:
        """Return {'verdict': str, 'rationale': str, 'model': str}."""
        ...

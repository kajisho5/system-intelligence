"""Research cache (docs/design/docs/06-research-engine.md, "Research cache").

A simple file-backed cache keyed by (provider, query), so repeated
diagnosis runs don't re-hit an external API for the same query within its
TTL. Local-filesystem only — not a distributed or multi-process-safe cache.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from system_intelligence.core.research import ResearchResult

DEFAULT_TTL = timedelta(hours=6)


def _cache_key(provider: str, query: str) -> str:
    return hashlib.sha256(f"{provider}:{query}".encode()).hexdigest()[:24]


@dataclass(frozen=True)
class ResearchCache:
    directory: Path
    ttl: timedelta = DEFAULT_TTL

    def get(self, provider: str, query: str) -> list[ResearchResult] | None:
        """Return cached results if present and within TTL, else None."""
        path = self.directory / f"{_cache_key(provider, query)}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(payload["cached_at"])
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            return None
        if datetime.now(UTC) - cached_at > self.ttl:
            return None
        return [ResearchResult.model_validate(item) for item in payload["results"]]

    def set(self, provider: str, query: str, results: list[ResearchResult]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{_cache_key(provider, query)}.json"
        payload = {
            "provider": provider,
            "query": query,
            "cached_at": datetime.now(UTC).isoformat(),
            "results": [r.model_dump(mode="json") for r in results],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

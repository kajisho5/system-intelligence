"""Research cache (docs/design/docs/06-research-engine.md, "Research cache").

A simple file-backed cache keyed by (provider, query, limit), so repeated
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

#: `si research`'s own default (`_RESEARCH_LIMIT_OPTION` in cli/main.py) --
#: used only as this cache's default when a caller doesn't pass one
#: explicitly, so existing single-limit call sites/tests keep working
#: unchanged.
DEFAULT_LIMIT = 10


def _cache_key(provider: str, query: str, limit: int) -> str:
    return hashlib.sha256(f"{provider}:{limit}:{query}".encode()).hexdigest()[:24]


@dataclass(frozen=True)
class ResearchCache:
    directory: Path
    ttl: timedelta = DEFAULT_TTL

    def get(
        self, provider: str, query: str, limit: int = DEFAULT_LIMIT
    ) -> list[ResearchResult] | None:
        """Return cached results if present and within TTL, else None.

        `limit` is part of the cache key, not applied after the fact: a
        provider's own `search(query, limit=...)` only ever fetches/returns
        up to `limit` results in the first place (`research/github.py`,
        `research/mcp_registry.py`), so a cache entry written for one limit
        can hold strictly fewer results than a larger limit just asked for
        -- reusing it across different limits either silently withheld
        results a caller explicitly asked for, or handed back more than a
        smaller limit allowed.
        """
        path = self.directory / f"{_cache_key(provider, query, limit)}.json"
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

    def set(
        self,
        provider: str,
        query: str,
        results: list[ResearchResult],
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{_cache_key(provider, query, limit)}.json"
        payload = {
            "provider": provider,
            "query": query,
            "limit": limit,
            "cached_at": datetime.now(UTC).isoformat(),
            "results": [r.model_dump(mode="json") for r in results],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

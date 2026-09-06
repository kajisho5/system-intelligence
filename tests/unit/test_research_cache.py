from datetime import timedelta
from pathlib import Path

from system_intelligence.core.research import ResearchResult
from system_intelligence.research.cache import ResearchCache


def _result(identifier: str) -> ResearchResult:
    return ResearchResult(
        query="q", provider="github", source=f"https://x/{identifier}", identifier=identifier
    )


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = ResearchCache(directory=tmp_path)
    assert cache.get("github", "nothing cached") is None


def test_cache_set_then_get_round_trips(tmp_path: Path) -> None:
    cache = ResearchCache(directory=tmp_path)
    results = [_result("a/a"), _result("b/b")]

    cache.set("github", "query", results)
    cached = cache.get("github", "query")

    assert cached is not None
    assert [r.identifier for r in cached] == ["a/a", "b/b"]


def test_cache_expires_after_ttl(tmp_path: Path) -> None:
    cache = ResearchCache(directory=tmp_path, ttl=timedelta(seconds=-1))
    cache.set("github", "query", [_result("a/a")])

    assert cache.get("github", "query") is None


def test_cache_is_keyed_by_provider_and_query(tmp_path: Path) -> None:
    cache = ResearchCache(directory=tmp_path)
    cache.set("github", "query-a", [_result("a/a")])

    assert cache.get("github", "query-b") is None
    assert cache.get("npm", "query-a") is None


def test_cache_corrupt_file_returns_none(tmp_path: Path) -> None:
    cache = ResearchCache(directory=tmp_path)
    cache.set("github", "query", [_result("a/a")])
    for path in tmp_path.glob("*.json"):
        path.write_text("not json", encoding="utf-8")

    assert cache.get("github", "query") is None

from system_intelligence.core.ids import stable_id


def test_stable_id_is_deterministic() -> None:
    assert stable_id("skill", "skills/a/SKILL.md") == stable_id("skill", "skills/a/SKILL.md")


def test_stable_id_differs_by_kind_and_parts() -> None:
    assert stable_id("skill", "x") != stable_id("document", "x")
    assert stable_id("skill", "a") != stable_id("skill", "b")


def test_stable_id_joins_multiple_parts() -> None:
    assert stable_id("dependency", "pypi", "pydantic") == "dependency:pypi:pydantic"

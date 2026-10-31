"""Ownership-map analysis (ECOSYSTEM_ROADMAP.md step 2, ADR-012).

`tests/fixtures/ownership/` holds trimmed excerpts of real files (only
`repo`/`status`/`owns` kept per component):

- `ecosystem-6e17ae9.json`: kajisho5/AI-video-production-OS `ecosystem.json`
  at 6e17ae9 (#77), which gave the delivery platform specs
  (配信プラットフォーム仕様) to publish-skill while ffmpeg-skill's
  `_platforms.py` held the table its `export` tool reads -- the overlap the
  owner resolved in #80 by moving the job to ffmpeg-skill.
- `ecosystem-ae8304e.json`: the same file at ae8304e (current main), after
  that decision. Its one planned component, nle-bridge-skill, owns the only
  job without an active owner.
- `ffmpeg-skill-2.22.1.provides.json`: four `provides` entries of
  ffmpeg-skill's contract as recorded in the OS's
  `registry/tests/fixtures/ffmpeg-skill.provides.json` at da6167d.
"""

import json
from pathlib import Path
from typing import Any

from system_intelligence.analysis.ownership import audit_ownership, normalize_name
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.contracts import ContractObservation
from system_intelligence.discovery.ownership import OwnershipObservation
from system_intelligence.integrations.ai_video_os import (
    INACTIVE_COMPONENT_STATUSES,
    load_capability_contract_schema,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ownership"
PLATFORM_JOB = "配信プラットフォーム仕様"
BINDING = {"job_capabilities": {PLATFORM_JOB: ["ffmpeg-skill.export"]}}


def _repository() -> Repository:
    return Repository(id="r1", name="repo", path=".")


def _map(document: Any, label: str = "map.json") -> OwnershipObservation:
    evidence = Evidence(kind=EvidenceKind.FILE, source=label, observation="read")
    return OwnershipObservation("file", label, evidence, document=document)


def _fixture_map(name: str) -> OwnershipObservation:
    return _map(json.loads((FIXTURES / name).read_text(encoding="utf-8")), name)


def _contract(document: Any, label: str = "contract.json") -> ContractObservation:
    evidence = Evidence(kind=EvidenceKind.FILE, source=label, observation="read")
    return ContractObservation("file", label, evidence, document=document)


def _ffmpeg_contract() -> ContractObservation:
    name = "ffmpeg-skill-2.22.1.provides.json"
    return _contract(json.loads((FIXTURES / name).read_text(encoding="utf-8")), name)


def _audit(
    *maps: OwnershipObservation,
    contracts: tuple[ContractObservation, ...] = (),
    inactive: tuple[str, ...] = INACTIVE_COMPONENT_STATUSES,
) -> list[Finding]:
    return audit_ownership(
        maps, _repository(), contracts, load_capability_contract_schema(), inactive
    )


def _pairs(findings: list[Finding]) -> list[tuple[str, str]]:
    return [(f.category, f.statement) for f in findings]


def test_no_sources_means_no_findings() -> None:
    assert _audit() == []


def test_historical_map_publish_ffmpeg_platform_table_overlap() -> None:
    """ECOSYSTEM_ROADMAP.md step 2's 'done when'."""
    findings = _audit(
        _fixture_map("ecosystem-6e17ae9.json"),
        _map(BINDING, ".si/ownership.json"),
        contracts=(_ffmpeg_contract(),),
    )

    [finding] = findings
    assert finding.category == "ownership_provider_overlap"
    assert finding.statement == (
        f"{PLATFORM_JOB!r} is owned by publish-skill (ecosystem-6e17ae9.json), but the "
        "capability contract from ffmpeg-skill-2.22.1.provides.json (ffmpeg-skill) provides "
        "'ffmpeg-skill.export', which .si/ownership.json binds to that job."
    )
    assert finding.severity == Severity.HIGH
    assert finding.confidence == Confidence.HIGH
    assert finding.affected_entity_ids == ["r1"]
    assert [(e.source, e.locator) for e in finding.evidence] == [
        ("ecosystem-6e17ae9.json", "/components/22/owns/1"),
        (".si/ownership.json", f"/job_capabilities/{PLATFORM_JOB}/0"),
        ("ffmpeg-skill-2.22.1.provides.json", "/provides/1"),
    ]
    assert "move it to ffmpeg-skill" in finding.suggested_actions[0]


def test_current_map_has_no_overlap_and_one_job_without_an_active_owner() -> None:
    findings = _audit(
        _fixture_map("ecosystem-ae8304e.json"),
        _map(BINDING, ".si/ownership.json"),
        contracts=(_ffmpeg_contract(),),
    )

    assert _pairs(findings) == [
        (
            "ownership_unowned_job",
            "'NLE連携(タイムライン受け渡し)' has no active owner: only nle-bridge-skill "
            "(planned) owns it.",
        )
    ]
    assert findings[0].severity == Severity.LOW
    assert findings[0].confidence == Confidence.VERIFIED


def test_inactive_statuses_are_the_callers_choice() -> None:
    assert _audit(_fixture_map("ecosystem-ae8304e.json"), inactive=()) == []


def test_two_owners_of_one_job_overlap() -> None:
    document = {
        "components": [
            {"repo": "publish-skill", "owns": ["配信先アップロード", PLATFORM_JOB]},
            {"repo": "ffmpeg-skill", "owns": ["FFmpeg実行", f" {PLATFORM_JOB} "]},
        ]
    }

    [finding] = _audit(_map(document))

    assert (finding.category, finding.statement) == (
        "ownership_overlap",
        f"{PLATFORM_JOB!r} is owned by 2 components: ffmpeg-skill (map.json), "
        "publish-skill (map.json).",
    )
    assert finding.severity == Severity.HIGH
    assert finding.confidence == Confidence.VERIFIED
    assert [e.locator for e in finding.evidence] == ["/components/0/owns/1", "/components/1/owns/1"]


def test_overlap_across_two_maps_and_name_key() -> None:
    first = _map({"components": [{"name": "a", "owns": ["Ｊob"]}]}, "one.json")
    second = _map({"components": [{"repo": "b", "owns": ["job"]}]}, "two.json")

    [finding] = _audit(first, second)

    assert finding.statement == "'Ｊob' is owned by 2 components: a (one.json), b (two.json)."


def test_the_same_owner_listed_twice_is_not_an_overlap() -> None:
    document = {"components": [{"repo": "x", "owns": ["job"]}]}

    assert _audit(_map(document, "a.json"), _map(document, "b.json")) == []


def test_provider_that_owns_the_job_is_not_an_overlap() -> None:
    document = {"components": [{"repo": "ffmpeg-skill", "owns": [PLATFORM_JOB]}]}

    assert _audit(_map(document), _map(BINDING), contracts=(_ffmpeg_contract(),)) == []


def test_provider_matched_by_package_name() -> None:
    contract = {
        "skill_id": "ingest",
        "skill": {"id": "ingest", "package": "ingest-skill"},
        "provides": [{"id": "ingest.fetch", "lifecycle": "EXPERIMENTAL", "tool_id": "i/f"}],
    }
    owned_by_package = {"components": [{"repo": "ingest-skill", "owns": ["URL素材取得"]}]}
    owned_by_agent = {"components": [{"repo": "video-production-agent", "owns": ["URL素材取得"]}]}
    binding = _map({"job_capabilities": {"URL素材取得": ["ingest.fetch"]}})

    assert _audit(_map(owned_by_package), binding, contracts=(_contract(contract),)) == []
    [finding] = _audit(_map(owned_by_agent), binding, contracts=(_contract(contract),))
    assert finding.category == "ownership_provider_overlap"
    assert "(ingest) provides 'ingest.fetch'" in finding.statement


def test_contract_with_schema_violations_is_not_compared() -> None:
    document = {"components": [{"repo": "publish-skill", "owns": [PLATFORM_JOB]}]}
    broken = {"skill": "ffmpeg-skill", "provides": [{"id": "ffmpeg-skill.export"}]}

    assert _audit(_map(document), _map(BINDING), contracts=(_contract(broken),)) == []


def test_bound_job_without_an_owner_is_unowned() -> None:
    document = {"components": [{"repo": "x", "owns": ["other"]}]}

    [finding] = _audit(_map(document), _map(BINDING, ".si/ownership.json"))

    assert (finding.category, finding.statement) == (
        "ownership_unowned_job",
        f"{PLATFORM_JOB!r} is bound to capabilities in .si/ownership.json but no ownership "
        "map gives it an owner.",
    )
    assert finding.severity == Severity.MEDIUM


def test_bindings_without_any_map_report_nothing() -> None:
    assert _audit(_map(BINDING), contracts=(_ffmpeg_contract(),)) == []


def test_unavailable_source() -> None:
    evidence = Evidence(kind=EvidenceKind.FILE, source="m.json", observation="missing")
    observation = OwnershipObservation("file", "m.json", evidence, error="could not be read")

    [finding] = _audit(observation)

    assert (finding.category, finding.statement) == (
        "ownership_map_unavailable",
        "Ownership map m.json is unavailable: could not be read",
    )


def test_invalid_values_are_named_by_pointer_and_the_rest_is_read() -> None:
    document = {
        "components": [
            "x",
            {"owns": ["a"]},
            {"repo": "p", "owns": "a"},
            {"repo": "q", "owns": ["", "job"]},
            {"repo": "r", "owns": ["job"]},
        ],
        "job_capabilities": {"job": "c", "a/b": [1]},
    }

    pairs = _pairs(_audit(_map(document)))

    assert [category for category, _ in pairs] == ["ownership_map_invalid"] * 6 + [
        "ownership_overlap"
    ]
    statements = "\n".join(statement for _, statement in pairs)
    for pointer in (
        "/components/0:",
        "/components/1:",
        "/components/2/owns:",
        "/components/3/owns/0:",
        "/job_capabilities/job:",
        "/job_capabilities/a~1b/0:",
    ):
        assert f"map.json at {pointer}" in statements


def test_non_object_documents_are_invalid() -> None:
    assert _pairs(_audit(_map([]), _map({"components": {}, "job_capabilities": []}))) == [
        (
            "ownership_map_invalid",
            "Ownership map map.json at /: expected an object; that value is ignored.",
        ),
        (
            "ownership_map_invalid",
            "Ownership map map.json at /components: expected an array; that value is ignored.",
        ),
        (
            "ownership_map_invalid",
            "Ownership map map.json at /job_capabilities: expected an "
            "object; that value is ignored.",
        ),
    ]


def test_normalize_name() -> None:
    assert normalize_name(" Ｆfmpeg-SKILL ") == "ffmpeg-skill"

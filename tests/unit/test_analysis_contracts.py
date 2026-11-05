"""Capability-contract validation against the bundled OS schema.

`tests/fixtures/contracts/` holds trimmed excerpts of real `contract --json`
output (only `tools`/`errors`/`manifest` and most `not_provided` entries cut):

- `artifacts-skill-0.3.0.contract.json`: kajisho5/artifacts-skill
  `build_contract()` at 953373b (v0.3.0), before "contract in the OS registry
  shape" (#62) -- no skill identity and no `provides`.
- `ingest-skill-0.1.0.contract.json`: kajisho5/ingest-skill `contract()` at
  3710c4f, before its own "contract in the OS registry shape" (#4) -- `skill`
  is a string, and `dependencies` lists a binary rather than a Skill.
- `ingest-skill-0.1.x.contract.json`: the same function on main after #4 and
  #9 (44013ce), which validates.

These are the two problems ECOSYSTEM_ROADMAP.md step 1 must surface as Findings.
"""

import json
from pathlib import Path
from typing import Any

from system_intelligence.analysis.contracts import (
    audit_capability_contracts,
    contract_identities,
    extract_contract_capabilities,
)
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import CapabilityStatus, Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.discovery.contracts import ContractObservation, read_contract_file
from system_intelligence.integrations.ai_video_os import (
    CAPABILITY_CONTRACT_SCHEMA_LABEL,
    load_capability_contract_schema,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"


def _repository() -> Repository:
    return Repository(id="r1", name="repo", path=".")


def _observation(document: Any, label: str = "contract.json") -> ContractObservation:
    evidence = Evidence(kind=EvidenceKind.FILE, source=label, observation="read")
    return ContractObservation("file", label, evidence, document=document)


def _audit(*observations: ContractObservation) -> list[tuple[str, str]]:
    findings = audit_capability_contracts(
        observations,
        _repository(),
        load_capability_contract_schema(),
        CAPABILITY_CONTRACT_SCHEMA_LABEL,
    )
    return [(f.category, f.statement) for f in findings]


def _fixture(name: str) -> ContractObservation:
    observation = read_contract_file(FIXTURES / name)
    # Use the file name as the label so statements do not depend on the checkout path.
    return ContractObservation(
        observation.kind, name, observation.evidence, document=observation.document
    )


def test_pre_os_shape_artifacts_contract_has_no_skill_identity() -> None:
    [(category, statement)] = _audit(_fixture("artifacts-skill-0.3.0.contract.json"))

    assert category == "capability_contract_violation"
    assert statement.startswith(
        "Capability contract from artifacts-skill-0.3.0.contract.json does not match "
        f"{CAPABILITY_CONTRACT_SCHEMA_LABEL} at /: matches none of the anyOf alternatives"
    )
    assert "'skill_id'" in statement and "'skill'" in statement


def test_pre_os_shape_ingest_contract_has_string_skill_and_binary_dependency() -> None:
    results = _audit(_fixture("ingest-skill-0.1.0.contract.json"))

    assert results == [
        (
            "capability_contract_violation",
            "Capability contract from ingest-skill-0.1.0.contract.json does not match "
            f"{CAPABILITY_CONTRACT_SCHEMA_LABEL} at /skill: expected object, got string",
        ),
        (
            "capability_contract_violation",
            "Capability contract from ingest-skill-0.1.0.contract.json does not match "
            f"{CAPABILITY_CONTRACT_SCHEMA_LABEL} at /dependencies/0: "
            "missing required property 'skill_id'",
        ),
        (
            "capability_contract_violation",
            "Capability contract from ingest-skill-0.1.0.contract.json does not match "
            f"{CAPABILITY_CONTRACT_SCHEMA_LABEL} at /dependencies/0: "
            "missing required property 'version_range'",
        ),
    ]


def test_current_ingest_contract_is_clean() -> None:
    assert _audit(_fixture("ingest-skill-0.1.x.contract.json")) == []


def test_violation_finding_is_verified_and_cites_contract_and_schema() -> None:
    [finding, *_] = audit_capability_contracts(
        [_fixture("ingest-skill-0.1.0.contract.json")],
        _repository(),
        load_capability_contract_schema(),
        CAPABILITY_CONTRACT_SCHEMA_LABEL,
    )

    assert finding.severity == Severity.HIGH
    assert finding.confidence == Confidence.VERIFIED
    assert finding.affected_entity_ids == ["r1"]
    contract_evidence, schema_evidence = finding.evidence
    assert contract_evidence.source.endswith("ingest-skill-0.1.0.contract.json")
    assert schema_evidence.source == CAPABILITY_CONTRACT_SCHEMA_LABEL
    assert schema_evidence.locator == "/skill"


def test_valid_contract_without_provides_is_a_low_finding() -> None:
    findings = audit_capability_contracts(
        [_observation({"skill_id": "x"}), _observation({"skill_id": "y", "provides": []})],
        _repository(),
        load_capability_contract_schema(),
    )

    assert [f.category for f in findings] == ["capability_contract_no_provides"] * 2
    assert all(f.severity == Severity.LOW for f in findings)


def test_non_object_document_is_a_violation() -> None:
    [(category, statement)] = _audit(_observation([1, 2]))

    assert category == "capability_contract_violation"
    assert statement.endswith("at /: expected object, got array")


def test_unavailable_source_becomes_a_finding(tmp_path: Path) -> None:
    observation = read_contract_file(tmp_path / "missing.json")

    [finding] = audit_capability_contracts([observation], _repository(), None)

    assert finding.category == "capability_contract_unavailable"
    assert finding.severity == Severity.MEDIUM
    assert finding.evidence == [observation.evidence]


def test_without_a_schema_only_availability_and_provides_are_checked() -> None:
    findings = audit_capability_contracts(
        [_observation({"skill": "a string"})], _repository(), schema=None
    )

    assert [f.category for f in findings] == ["capability_contract_no_provides"]


def test_no_observations_no_findings() -> None:
    assert audit_capability_contracts([], _repository(), load_capability_contract_schema()) == []


def test_statements_are_stable_across_runs() -> None:
    """`si watch` matches findings by (category, statement)."""
    document = json.loads((FIXTURES / "ingest-skill-0.1.0.contract.json").read_text("utf-8"))

    assert _audit(_observation(document)) == _audit(_observation(document))


def test_valid_contract_provides_become_capabilities() -> None:
    [_, observation] = [
        _fixture("ingest-skill-0.1.0.contract.json"),
        _fixture("ingest-skill-0.1.x.contract.json"),
    ]

    capabilities = extract_contract_capabilities(
        [observation], _repository(), load_capability_contract_schema()
    )

    assert [c.name for c in capabilities] == [
        "ingest.offload",
        "ingest.verify",
        "ingest.inventory",
        "ingest.fetch",
    ]
    offload = capabilities[0]
    assert offload.id == "capability:contract:ingest:ingest.offload"
    assert offload.provider_ids == ["r1"]
    assert offload.status == CapabilityStatus.AVAILABLE
    assert offload.confidence == Confidence.HIGH
    assert offload.description == "Tool ingest/offload"
    [evidence] = offload.evidence
    assert (evidence.source, evidence.locator) == (
        "ingest-skill-0.1.x.contract.json",
        "/provides/0",
    )


def test_contract_with_violations_contributes_no_capabilities() -> None:
    observation = _fixture("ingest-skill-0.1.0.contract.json")
    schema = load_capability_contract_schema()

    assert extract_contract_capabilities([observation], _repository(), schema) == []
    # Without a schema nothing is rejected, so its provides are read.
    assert extract_contract_capabilities([observation], _repository(), None) != []


def test_lifecycle_sets_capability_status() -> None:
    document = {
        "skill_id": "x",
        "provides": [
            {"id": f"x.{lifecycle.lower()}", "lifecycle": lifecycle, "tool_id": "x/t"}
            for lifecycle in ("STABLE", "EXPERIMENTAL", "DEPRECATED", "PROPOSED", "RETIRED")
        ]
        + [{"id": "x.none", "tool_id": "x/t"}, {"tool_id": "no id"}],
    }

    capabilities = extract_contract_capabilities([_observation(document)], _repository())

    assert [(c.name, c.status) for c in capabilities] == [
        ("x.stable", CapabilityStatus.AVAILABLE),
        ("x.experimental", CapabilityStatus.AVAILABLE),
        ("x.deprecated", CapabilityStatus.DEPRECATED),
        ("x.proposed", CapabilityStatus.MISSING),
        ("x.retired", CapabilityStatus.MISSING),
        ("x.none", CapabilityStatus.UNKNOWN),
    ]


def test_same_contract_from_two_sources_is_one_capability_with_both_sources() -> None:
    document = {"skill_id": "x", "provides": [{"id": "x.a", "lifecycle": "STABLE", "tool_id": "t"}]}

    [capability] = extract_contract_capabilities(
        [_observation(document, "a.json"), _observation(document, "b.json")], _repository()
    )

    assert [e.source for e in capability.evidence] == ["a.json", "b.json"]


def test_unavailable_and_non_object_contracts_contribute_nothing(tmp_path: Path) -> None:
    observations = [read_contract_file(tmp_path / "missing.json"), _observation([1])]

    assert extract_contract_capabilities(observations, _repository()) == []


def test_contract_identities() -> None:
    assert contract_identities(
        {"skill_id": "ingest", "id": "ingest", "skill": {"id": "ingest", "package": "ingest-skill"}}
    ) == ["ingest", "ingest-skill"]
    assert contract_identities({"skill": {"id": "ffmpeg-skill"}}) == ["ffmpeg-skill"]
    assert contract_identities({"skill": "x", "id": " ", "skill_id": 3}) == []
    assert contract_identities([]) == []

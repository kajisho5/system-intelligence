"""Capability-contract validation: collected contract documents -> Findings.

Takes the observations `discovery/contracts.py` collected and checks each
document against a Capability Contract JSON Schema supplied by the caller
(the CLI passes the bundled one, or `--contract-schema`; see ADR-011). This
module itself knows no particular ecosystem's schema -- it validates
against whatever schema it is handed, with `analysis/json_schema.py`.

Finding categories:

- `capability_contract_violation` -- one per schema violation, with the
  JSON Pointer of the offending value. Deterministic, so `verified`.
- `capability_contract_unavailable` -- the source could not be read or run,
  or did not yield JSON (including a malformed `.si/contracts.json`).
- `capability_contract_no_provides` -- the document validates but declares
  no capabilities (`provides` missing or empty), so a registry reading it
  learns nothing about what the component offers.

No sources means no findings: contract discovery is opt-in, never inferred.

`extract_contract_capabilities` reads every `provides` entry of a contract
that validates into a `Capability` entity (ADR-012), so contract-declared
capabilities join the Snapshot next to the ones Skills/Agents declare.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from system_intelligence.analysis.json_schema import validate
from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import CapabilityStatus, Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.ids import stable_id
from system_intelligence.discovery.contracts import ContractObservation

#: A `provides[].lifecycle` value -> what it says about availability. Only a
#: capability that can be used today counts as available (`capability_gap`
#: treats nothing else as satisfying a requirement); an unknown or missing
#: lifecycle is `unknown`, never guessed.
_STATUS_BY_LIFECYCLE: dict[str, CapabilityStatus] = {
    "STABLE": CapabilityStatus.AVAILABLE,
    "EXPERIMENTAL": CapabilityStatus.AVAILABLE,
    "DEPRECATED": CapabilityStatus.DEPRECATED,
    "PROPOSED": CapabilityStatus.MISSING,
    "RETIRED": CapabilityStatus.MISSING,
}


def _schema_evidence(schema_label: str, pointer: str, message: str) -> Evidence:
    return Evidence(
        kind=EvidenceKind.FILE,
        source=schema_label,
        locator=pointer or "/",
        observation=f"validated against this schema: {message}",
        confidence=Confidence.VERIFIED,
    )


def _unavailable(observation: ContractObservation, repository: Repository) -> Finding:
    return Finding(
        category="capability_contract_unavailable",
        severity=Severity.MEDIUM,
        statement=f"Capability contract from {observation.label} is unavailable: "
        f"{observation.error}",
        confidence=Confidence.VERIFIED,
        affected_entity_ids=[repository.id],
        evidence=[observation.evidence],
        suggested_actions=[
            "Make the contract source produce one JSON document "
            "(check the path or command, and run it by hand to see its output)."
        ],
    )


def audit_capability_contracts(
    observations: Sequence[ContractObservation],
    repository: Repository,
    schema: Mapping[str, Any] | None = None,
    schema_label: str = "capability contract schema",
) -> list[Finding]:
    """Findings for every collected contract source.

    `schema` must already have passed `json_schema.check_supported`. When
    it is `None`, documents are not schema-checked: only unavailable
    sources and missing `provides` are reported.
    """
    findings: list[Finding] = []
    for observation in observations:
        if observation.error is not None:
            findings.append(_unavailable(observation, repository))
            continue
        document = observation.document

        violations = validate(document, schema) if schema is not None else []
        for violation in violations:
            location = violation.pointer or "/"
            findings.append(
                Finding(
                    category="capability_contract_violation",
                    severity=Severity.HIGH,
                    statement=f"Capability contract from {observation.label} does not match "
                    f"{schema_label} at {location}: {violation.message}",
                    confidence=Confidence.VERIFIED,
                    affected_entity_ids=[repository.id],
                    evidence=[
                        observation.evidence,
                        _schema_evidence(schema_label, violation.pointer, violation.message),
                    ],
                    suggested_actions=[
                        f"Change the contract so {location} matches {schema_label}."
                    ],
                )
            )
        if violations or not isinstance(document, Mapping):
            continue

        provides = document.get("provides")
        if not isinstance(provides, list) or not provides:
            findings.append(
                Finding(
                    category="capability_contract_no_provides",
                    severity=Severity.LOW,
                    statement=f"Capability contract from {observation.label} declares no "
                    "capabilities ('provides' is missing or empty).",
                    confidence=Confidence.VERIFIED,
                    affected_entity_ids=[repository.id],
                    evidence=[observation.evidence],
                    suggested_actions=[
                        "List the capabilities this component offers under 'provides'."
                    ],
                )
            )
    return findings


def contract_identities(document: Any) -> list[str]:
    """Every name a contract document gives its component, in a stable order.

    The three skill-identity shapes the ecosystem uses (flat `skill_id`,
    flat `id`, nested `skill.id`) plus `skill.package` (a Python package
    name such as `ingest-skill`, which is what an ownership map usually
    calls the component). Non-string and empty values are skipped;
    duplicates are listed once.
    """
    if not isinstance(document, Mapping):
        return []
    candidates: list[Any] = [document.get("skill_id"), document.get("id")]
    skill = document.get("skill")
    if isinstance(skill, Mapping):
        candidates += [skill.get("id"), skill.get("package")]
    identities: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip() and candidate not in identities:
            identities.append(candidate)
    return identities


def provided_capability_ids(document: Any) -> list[tuple[int, str]]:
    """`(index, id)` for every `provides` entry that names a capability by a non-empty string."""
    if not isinstance(document, Mapping):
        return []
    provides = document.get("provides")
    if not isinstance(provides, list):
        return []
    return [
        (index, entry["id"])
        for index, entry in enumerate(provides)
        if isinstance(entry, Mapping) and isinstance(entry.get("id"), str) and entry["id"].strip()
    ]


def extract_contract_capabilities(
    observations: Sequence[ContractObservation],
    repository: Repository,
    schema: Mapping[str, Any] | None = None,
) -> list[Capability]:
    """One `Capability` per `provides` entry of every contract that validates.

    A contract with schema violations contributes none: its problems are
    already Findings, and an entry the schema rejects is not a fact to
    build on. The provider is the target `repository` (the contract is
    the component describing itself); the id is keyed on the contract's
    first identity and the capability id, so the same capability read
    from two sources of the same contract is one entity with both
    sources as evidence. Status follows `lifecycle`; confidence is `high`,
    not `verified`: the component declares it, nothing here ran it.
    """
    by_id: dict[str, Capability] = {}
    for observation in observations:
        document = observation.document
        if observation.error is not None or not isinstance(document, Mapping):
            continue
        if schema is not None and validate(document, schema):
            continue
        identities = contract_identities(document)
        owner = identities[0] if identities else observation.label
        for index, capability_id in provided_capability_ids(document):
            entry = document["provides"][index]
            lifecycle = entry.get("lifecycle")
            status = (
                _STATUS_BY_LIFECYCLE.get(lifecycle, CapabilityStatus.UNKNOWN)
                if isinstance(lifecycle, str)
                else CapabilityStatus.UNKNOWN
            )
            tool_id = entry.get("tool_id")
            evidence = Evidence(
                kind=observation.evidence.kind,
                source=observation.label,
                locator=f"/provides/{index}",
                observation=f"{owner!r} declares that it provides {capability_id!r}"
                + (f" (lifecycle {lifecycle})" if isinstance(lifecycle, str) else ""),
                confidence=Confidence.HIGH,
            )
            entity_id = stable_id("capability", "contract", owner, capability_id)
            existing = by_id.get(entity_id)
            if existing is not None:
                by_id[entity_id] = existing.model_copy(
                    update={"evidence": [*existing.evidence, evidence]}
                )
                continue
            by_id[entity_id] = Capability(
                id=entity_id,
                name=capability_id,
                description=f"Tool {tool_id}" if isinstance(tool_id, str) and tool_id else None,
                provider_ids=[repository.id],
                status=status,
                confidence=Confidence.HIGH,
                evidence=[evidence],
            )
    return list(by_id.values())

"""Ownership-map analysis: overlapping and unowned jobs (ADR-012).

Reads the ownership documents `discovery/ownership.py` collected -- each
gives jobs to components (`components[].owns`) and may bind jobs to the
capability ids that realize them (`job_capabilities`) -- together with the
Capability Contracts `discovery/contracts.py` collected.

Finding categories:

- `ownership_overlap` -- one job is owned by two or more components.
- `ownership_provider_overlap` -- a job is owned by one component, but
  another component's Capability Contract provides a capability that an
  ownership document binds to that job (e.g. a map giving the platform
  table to publish-skill while ffmpeg-skill's contract provides
  `ffmpeg-skill.export`, the tool that holds it).
- `ownership_unowned_job` -- a job whose every owner has an inactive
  status (the caller says which statuses mean "does not exist yet"; the
  CLI passes the AI Video Production OS's `planned`), or a job bound to
  capabilities that no ownership map gives to anyone.
- `ownership_map_unavailable` -- a source could not be read or is not
  JSON (including a malformed `.si/ownership.json`).
- `ownership_map_invalid` -- one value has the wrong shape, named by its
  JSON Pointer; the rest of the document is still read.

Jobs and component names are compared exactly, after Unicode NFKC
normalization, trimming and case folding -- never by similarity (ADR-002).
No sources means no findings: ownership analysis is opt-in, never inferred.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from system_intelligence.analysis.contracts import contract_identities, provided_capability_ids
from system_intelligence.analysis.json_schema import validate
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.contracts import ContractObservation
from system_intelligence.discovery.ownership import OwnershipObservation


def normalize_name(text: str) -> str:
    """The comparison key for a job or component name."""
    return unicodedata.normalize("NFKC", text).strip().casefold()


@dataclass(frozen=True)
class _Claim:
    job: str
    owner: str
    status: str | None
    source: str
    pointer: str


@dataclass(frozen=True)
class _Binding:
    job: str
    capability_id: str
    source: str
    pointer: str


@dataclass
class _Ownership:
    claims: dict[str, list[_Claim]]
    bindings: dict[str, list[_Binding]]
    has_components: bool
    findings: list[Finding]


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _is_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finding(
    category: str,
    severity: Severity,
    statement: str,
    confidence: Confidence,
    repository: Repository,
    evidence: list[Evidence],
    action: str,
) -> Finding:
    return Finding(
        category=category,
        severity=severity,
        statement=statement,
        confidence=confidence,
        affected_entity_ids=[repository.id],
        evidence=evidence,
        suggested_actions=[action],
    )


def _claim_evidence(claim: _Claim) -> Evidence:
    return Evidence(
        kind=EvidenceKind.FILE,
        source=claim.source,
        locator=claim.pointer,
        observation=f"{claim.owner!r} owns {claim.job!r}"
        + (f" (status {claim.status})" if claim.status else ""),
        confidence=Confidence.VERIFIED,
    )


def _binding_evidence(binding: _Binding) -> Evidence:
    return Evidence(
        kind=EvidenceKind.FILE,
        source=binding.source,
        locator=binding.pointer,
        observation=f"{binding.job!r} is realized by the capability {binding.capability_id!r}",
        confidence=Confidence.VERIFIED,
    )


def _read_documents(
    observations: Sequence[OwnershipObservation], repository: Repository
) -> _Ownership:
    result = _Ownership(claims={}, bindings={}, has_components=False, findings=[])

    def invalid(observation: OwnershipObservation, pointer: str, problem: str) -> None:
        result.findings.append(
            _finding(
                "ownership_map_invalid",
                Severity.MEDIUM,
                f"Ownership map {observation.label} at {pointer}: {problem}; that value is "
                "ignored.",
                Confidence.VERIFIED,
                repository,
                [
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=observation.label,
                        locator=pointer,
                        observation=problem,
                        confidence=Confidence.VERIFIED,
                    )
                ],
                f"Fix {pointer} in {observation.label}.",
            )
        )

    for observation in observations:
        if observation.error is not None:
            result.findings.append(
                _finding(
                    "ownership_map_unavailable",
                    Severity.MEDIUM,
                    f"Ownership map {observation.label} is unavailable: {observation.error}",
                    Confidence.VERIFIED,
                    repository,
                    [observation.evidence],
                    "Make the ownership map one readable JSON document "
                    "(check the path and the JSON).",
                )
            )
            continue
        document = observation.document
        if not isinstance(document, Mapping):
            invalid(observation, "/", "expected an object")
            continue

        components = document.get("components")
        if components is not None and not isinstance(components, list):
            invalid(observation, "/components", "expected an array")
        elif isinstance(components, list):
            for index, component in enumerate(components):
                pointer = f"/components/{index}"
                if not isinstance(component, Mapping):
                    invalid(observation, pointer, "expected an object")
                    continue
                owner = component.get("name", component.get("repo"))
                if not _is_name(owner):
                    invalid(observation, pointer, "names no component ('name' or 'repo')")
                    continue
                result.has_components = True
                status = component.get("status")
                owns = component.get("owns", [])
                if not isinstance(owns, list):
                    invalid(observation, f"{pointer}/owns", "expected an array of job names")
                    continue
                for job_index, job in enumerate(owns):
                    job_pointer = f"{pointer}/owns/{job_index}"
                    if not _is_name(job):
                        invalid(observation, job_pointer, "expected a non-empty job name")
                        continue
                    result.claims.setdefault(normalize_name(job), []).append(
                        _Claim(
                            job=job.strip(),
                            owner=owner.strip(),
                            status=status if isinstance(status, str) else None,
                            source=observation.label,
                            pointer=job_pointer,
                        )
                    )

        bindings = document.get("job_capabilities")
        if bindings is not None and not isinstance(bindings, Mapping):
            invalid(observation, "/job_capabilities", "expected an object")
        elif isinstance(bindings, Mapping):
            for job, capability_ids in bindings.items():
                pointer = f"/job_capabilities/{_escape(str(job))}"
                if not _is_name(job):
                    invalid(observation, pointer, "expected a non-empty job name")
                    continue
                if not isinstance(capability_ids, list):
                    invalid(observation, pointer, "expected an array of capability ids")
                    continue
                for cap_index, capability_id in enumerate(capability_ids):
                    if not _is_name(capability_id):
                        invalid(observation, f"{pointer}/{cap_index}", "expected a capability id")
                        continue
                    result.bindings.setdefault(normalize_name(job), []).append(
                        _Binding(
                            job=job.strip(),
                            capability_id=capability_id.strip(),
                            source=observation.label,
                            pointer=f"{pointer}/{cap_index}",
                        )
                    )
    return result


def _owners(claims: list[_Claim]) -> dict[str, _Claim]:
    """Distinct owners by comparison key, first claim kept (stable, file order)."""
    owners: dict[str, _Claim] = {}
    for claim in claims:
        owners.setdefault(normalize_name(claim.owner), claim)
    return owners


def _describe_owners(owners: Mapping[str, _Claim]) -> str:
    return ", ".join(
        f"{claim.owner} ({claim.source})"
        for claim in sorted(owners.values(), key=lambda c: normalize_name(c.owner))
    )


def _overlaps(ownership: _Ownership, repository: Repository) -> list[Finding]:
    findings: list[Finding] = []
    for claims in ownership.claims.values():
        owners = _owners(claims)
        if len(owners) < 2:
            continue
        job = claims[0].job
        findings.append(
            _finding(
                "ownership_overlap",
                Severity.HIGH,
                f"{job!r} is owned by {len(owners)} components: {_describe_owners(owners)}.",
                Confidence.VERIFIED,
                repository,
                [_claim_evidence(claim) for claim in claims],
                f"Give {job!r} to exactly one component and hand it over from the others.",
            )
        )
    return findings


def _unowned(
    ownership: _Ownership, repository: Repository, inactive_statuses: Collection[str]
) -> list[Finding]:
    inactive = {normalize_name(status) for status in inactive_statuses}
    findings: list[Finding] = []
    if inactive:
        for claims in ownership.claims.values():
            owners = _owners(claims)
            if not all(
                claim.status is not None and normalize_name(claim.status) in inactive
                for claim in owners.values()
            ):
                continue
            job = claims[0].job
            described = ", ".join(
                f"{claim.owner} ({claim.status})"
                for claim in sorted(owners.values(), key=lambda c: normalize_name(c.owner))
            )
            findings.append(
                _finding(
                    "ownership_unowned_job",
                    Severity.LOW,
                    f"{job!r} has no active owner: only {described} owns it.",
                    Confidence.VERIFIED,
                    repository,
                    [_claim_evidence(claim) for claim in claims],
                    f"Build the owner of {job!r}, or hand the job to an active component.",
                )
            )
    if ownership.has_components:
        for key, bindings in ownership.bindings.items():
            if key in ownership.claims:
                continue
            job = bindings[0].job
            findings.append(
                _finding(
                    "ownership_unowned_job",
                    Severity.MEDIUM,
                    f"{job!r} is bound to capabilities in {bindings[0].source} but no ownership "
                    "map gives it an owner.",
                    Confidence.VERIFIED,
                    repository,
                    [_binding_evidence(binding) for binding in bindings],
                    f"Give {job!r} to one component in the ownership map.",
                )
            )
    return findings


def _provider_overlaps(
    ownership: _Ownership,
    contracts: Sequence[ContractObservation],
    contract_schema: Mapping[str, Any] | None,
    repository: Repository,
) -> list[Finding]:
    by_capability: dict[str, list[tuple[str, _Binding]]] = {}
    for key, bindings in ownership.bindings.items():
        for binding in bindings:
            by_capability.setdefault(binding.capability_id, []).append((key, binding))

    findings: list[Finding] = []
    for observation in contracts:
        document = observation.document
        if observation.error is not None or not isinstance(document, Mapping):
            continue
        if contract_schema is not None and validate(document, contract_schema):
            continue  # its problems are already capability_contract_violation findings
        identities = contract_identities(document)
        if not identities:
            continue
        identity_keys = {normalize_name(identity) for identity in identities}

        # job key -> the provides entries bound to it, in contract order
        conflicts: dict[str, list[tuple[int, str, _Binding]]] = {}
        for index, capability_id in provided_capability_ids(document):
            for key, binding in by_capability.get(capability_id, []):
                owners = _owners(ownership.claims.get(key, []))
                if not owners or identity_keys & owners.keys():
                    continue
                conflicts.setdefault(key, []).append((index, capability_id, binding))

        provider = identities[0]
        for key, entries in conflicts.items():
            owners = _owners(ownership.claims[key])
            job = ownership.claims[key][0].job
            capability_ids = list(dict.fromkeys(capability_id for _, capability_id, _ in entries))
            sources = sorted({binding.source for _, _, binding in entries})
            evidence = [
                *(_claim_evidence(claim) for claim in ownership.claims[key]),
                *(_binding_evidence(binding) for _, _, binding in entries),
                *(
                    Evidence(
                        kind=observation.evidence.kind,
                        source=observation.label,
                        locator=f"/provides/{index}",
                        observation=f"{provider!r} declares that it provides {capability_id!r}",
                        confidence=Confidence.HIGH,
                    )
                    for index, capability_id, _ in entries
                ),
            ]
            findings.append(
                _finding(
                    "ownership_provider_overlap",
                    Severity.HIGH,
                    f"{job!r} is owned by {_describe_owners(owners)}, but the capability "
                    f"contract from {observation.label} ({provider}) provides "
                    f"{', '.join(repr(c) for c in capability_ids)}, which "
                    f"{', '.join(sources)} binds to that job.",
                    Confidence.HIGH,
                    repository,
                    evidence,
                    f"Decide who owns {job!r}: move it to {provider} in the ownership map, "
                    f"or hand the capability over to its owner.",
                )
            )
    return findings


def audit_ownership(
    observations: Sequence[OwnershipObservation],
    repository: Repository,
    contracts: Sequence[ContractObservation] = (),
    contract_schema: Mapping[str, Any] | None = None,
    inactive_statuses: Collection[str] = (),
) -> list[Finding]:
    """Findings for every collected ownership document.

    `contracts` are compared with `job_capabilities` bindings; only those
    that validate against `contract_schema` (when given) are used, as for
    `extract_contract_capabilities`. `inactive_statuses` are the component
    statuses that mean the owner does not exist yet; empty by default, so
    this module assumes no ecosystem's vocabulary (ADR-001).
    """
    if not observations:
        return []
    ownership = _read_documents(observations, repository)
    return [
        *ownership.findings,
        *_overlaps(ownership, repository),
        *_provider_overlaps(ownership, contracts, contract_schema, repository),
        *_unowned(ownership, repository, inactive_statuses),
    ]

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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from system_intelligence.analysis.json_schema import validate
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.contracts import ContractObservation


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

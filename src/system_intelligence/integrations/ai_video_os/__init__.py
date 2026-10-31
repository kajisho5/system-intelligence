"""AI Video Production OS reference integration.

Two pieces so far:

- the OS's Capability Contract JSON Schema
  (`capability_contract.schema.json`), bundled verbatim so `si diagnose
  --contract-file/--contract-command` can validate a contract with no OS
  checkout at hand (ADR-011). It is the CLI's default contract schema;
  `--contract-schema` replaces it with any other schema file, which is how
  a target that is not part of the OS is checked against its own.
- `INACTIVE_COMPONENT_STATUSES`: the `ecosystem.json` component statuses
  that mean the repository does not exist yet, so a job only such a
  component owns is reported as unowned (ADR-012).

Provenance: kajisho5/AI-video-production-OS
`registry/capability_contract.schema.json` at commit
da6167d402039cf363edb8a6580cacf49dc06922 (2026-10-30), copied byte for
byte. When the OS changes the schema, copy it again and update this line.

Nothing in core, discovery, analysis, ... imports this package (see
`integrations/__init__.py`); only the CLI does, to pick the default.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

SCHEMA_FILENAME = "capability_contract.schema.json"
#: How Findings name this schema (stable across runs, unlike a file path).
CAPABILITY_CONTRACT_SCHEMA_LABEL = "the AI Video Production OS capability contract schema"


#: `ecosystem.json`'s own `$comment`: a `"status": "planned"` component is not
#: installed at all -- its repository does not exist yet.
INACTIVE_COMPONENT_STATUSES: tuple[str, ...] = ("planned",)


def load_capability_contract_schema() -> dict[str, Any]:
    """The bundled OS Capability Contract schema, parsed."""
    text = resources.files(__name__).joinpath(SCHEMA_FILENAME).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema

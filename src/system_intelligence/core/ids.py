"""Deterministic identifiers for entities that must be recognizable across scans.

`Entity.id` defaults to a random UUID (see `core.entities`), which is fine
for records with no persistent identity across runs (Evidence, Findings).
It is wrong for anything a diff or history view needs to recognize as "the
same thing" between two scans of the same target — a Component, Capability,
or Dependency whose id changes every scan would make every re-scan of an
*unchanged* repository look like a full replacement.

Callers that discover or derive such entities should pass an explicit `id=`
computed with `stable_id`, keyed on content that is itself stable across
scans (a file path, a capability name, an ecosystem+package pair) rather
than accepting the random default.
"""

from __future__ import annotations


def stable_id(kind: str, *parts: str) -> str:
    """Build a deterministic id from a kind prefix and one or more stable parts."""
    return ":".join((kind, *parts))

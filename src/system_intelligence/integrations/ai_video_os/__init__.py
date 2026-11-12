"""AI Video Production OS reference integration.

Four pieces so far:

- the OS's Capability Contract JSON Schema
  (`capability_contract.schema.json`), bundled verbatim so `si diagnose
  --contract-file/--contract-command` can validate a contract with no OS
  checkout at hand (ADR-011). It is the CLI's default contract schema;
  `--contract-schema` replaces it with any other schema file, which is how
  a target that is not part of the OS is checked against its own.
- `INACTIVE_COMPONENT_STATUSES`: the `ecosystem.json` component statuses
  that mean the repository does not exist yet, so a job only such a
  component owns is reported as unowned (ADR-012).
- the roadmap conventions `si roadmap-drift` reads (ADR-015): each
  repository's `ECOSYSTEM_ROADMAP.md`, and the documents that say what has
  shipped (`SKILL.md` at the root or under `skills/<repo>/`, `CHANGELOG.md`).
- `FIELD_READINESS_COLUMNS`: the columns of `si diagnose --field` (ADR-016),
  from the 2026-11-05 field review (resume after a stop, progress events,
  error classes, long-file tests, hardware encoder use, alpha and loudness
  outputs), each with the contract keys and the CI pattern that state it.

Provenance: kajisho5/AI-video-production-OS
`registry/capability_contract.schema.json` at commit
da6167d402039cf363edb8a6580cacf49dc06922 (2026-10-30), copied byte for
byte. When the OS changes the schema, copy it again and update this line.

Nothing in core, discovery, analysis, ... imports this package (see
`integrations/__init__.py`); only the CLI does, to pick the default.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import Any

from system_intelligence.analysis.field_readiness import ReadinessColumn

SCHEMA_FILENAME = "capability_contract.schema.json"
#: How Findings name this schema (stable across runs, unlike a file path).
CAPABILITY_CONTRACT_SCHEMA_LABEL = "the AI Video Production OS capability contract schema"


#: `ecosystem.json`'s own `$comment`: a `"status": "planned"` component is not
#: installed at all -- its repository does not exist yet.
INACTIVE_COMPONENT_STATUSES: tuple[str, ...] = ("planned",)


#: Each ecosystem repository's roadmap: numbered checkbox steps, one pull request
#: each, ticked by linking it.
ROADMAP_FILENAME = "ECOSYSTEM_ROADMAP.md"
#: Where a repository says what has shipped; `{repo}` is the repository name.
SHIPPED_FEATURE_DOCUMENTS: tuple[str, ...] = ("SKILL.md", "skills/{repo}/SKILL.md", "CHANGELOG.md")


def _ci_words(*phrases: str) -> str:
    """A CI pattern for whole phrases, also inside identifiers.

    Each phrase (words separated by spaces) matches as `long form`,
    `long-form`, `long_form` or `longform` between non-letters (so
    `test_long_form` counts and `longformat` does not), and as CamelCase
    (`LongFormTests`), with an optional plural `s`. Matched case-insensitively
    except the CamelCase form.
    """
    lower = "|".join(
        "[ _-]?".join(re.escape(word) for word in phrase.split()) for phrase in phrases
    )
    camel = "|".join(
        "".join(re.escape(word[:1].upper() + word[1:]) for word in phrase.split())
        for phrase in phrases
    )
    return rf"(?<![a-z])(?:{lower})s?(?![a-z])|(?-i:(?:{camel})s?(?![a-z]))"


FIELD_READINESS_COLUMNS: tuple[ReadinessColumn, ...] = (
    ReadinessColumn(
        id="resume",
        label="Resume after a stop",
        description="A stopped run continues where it stopped instead of starting over.",
        contract_keys=("resume", "resumable", "long_inputs/resume", "long_recordings/resumable"),
        ci_pattern=_ci_words("resume", "resumed", "resumable", "resuming"),
    ),
    ReadinessColumn(
        id="progress_events",
        label="Progress events",
        description="Machine-readable progress while a run works (step, percent, ETA).",
        contract_keys=("progress", "progress_events"),
        # `--no-progress`, `NO_PROGRESS`, "no progress" and `cancel-in-progress` turn
        # output or runs off; they test nothing.
        ci_pattern=rf"(?<!no-)(?<!no_)(?<!no )(?<!in-)(?:{_ci_words('progress')})",
    ),
    ReadinessColumn(
        id="error_classes",
        label="Error classes",
        description="Every error code mapped to a class the caller can act on.",
        contract_keys=("error_classes", "errors/classes"),
        ci_pattern=_ci_words("error class", "error classes"),
    ),
    ReadinessColumn(
        id="long_file_tests",
        label="Long-file tests",
        description="CI runs a test on a long input (hours of media).",
        ci_pattern=_ci_words(
            "long file",
            "long form",
            "long input",
            "long recording",
            "long video",
            "long source",
            "long programme",
            "hour long",
        )
        + r"|(?<![0-9a-z])[0-9]+[ -]?hours?(?![a-z])",
    ),
    ReadinessColumn(
        id="hardware_encoder",
        label="Hardware encoder use",
        description="Encodes on a hardware encoder (VideoToolbox, NVENC, QSV, VAAPI) when present.",
        contract_keys=(
            "hardware",
            "hardware_encoders",
            "hw",
            "hwaccel",
            "gpu_encoders",
            "proxy/hardware",
        ),
        ci_pattern=_ci_words(
            "video toolbox",
            "nvenc",
            "qsv",
            "vaapi",
            "hwaccel",
            "hardware encoder",
            "hardware encoding",
        )
        + r"|--hw(?![a-z])",
    ),
    ReadinessColumn(
        id="alpha_output",
        label="Alpha output",
        description="Writes outputs that keep an alpha channel.",
        contract_keys=("alpha", "alpha_mode", "alpha_output", "alpha_outputs", "keep_alpha"),
        ci_pattern=_ci_words("alpha"),
    ),
    ReadinessColumn(
        id="loudness_output",
        label="Loudness output",
        description="Writes loudness-targeted audio or loudness measurements with its output.",
        contract_keys=(
            "loudness",
            "loudness_versions",
            "loudness_targets",
            "audio_delivery/loudness_versions",
        ),
        ci_pattern=_ci_words("loudness", "lufs", "loudnorm", "ebur128"),
    ),
)


def load_capability_contract_schema() -> dict[str, Any]:
    """The bundled OS Capability Contract schema, parsed."""
    text = resources.files(__name__).joinpath(SCHEMA_FILENAME).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema

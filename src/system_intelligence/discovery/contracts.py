"""Capability-contract discovery: collect a target's machine-readable contract output.

A Capability Contract is the JSON document a component publishes about
itself (identity, version, the capabilities it `provides`, dependencies,
self-declared non-responsibilities) -- typically printed by a
`<tool> contract --json` command. This module only *collects* such
documents; `analysis/contracts.py` validates them against a schema.

Three sources, in order of preference (ADR-011):

1. **`.si/contracts.json` in the target** (checked-in, static, read
   automatically): `{"contracts": [{"path": "contract.json"}]}`. The
   same opt-in `.si/` convention `.si/requirements.json` uses. Each path
   must be relative and stay inside the target root. Deliberately
   *paths only* -- a file checked into an untrusted repository can never
   make System Intelligence run a command.
2. **`--contract-file`** (static, operator-supplied): a contract document
   captured elsewhere (a Skill's own CI, an earlier sandboxed run).
3. **`--contract-command`** (operator opt-in only): run a command the
   operator names, e.g. `ingest contract --json`. Never inferred from the
   target. Run as an argv list with no shell, `stdin` closed, a timeout,
   a minimal environment (no tokens or other secrets from the caller's
   environment) and a fresh empty temporary working directory -- never the
   target checkout, so nothing in it is picked up from the working
   directory (e.g. a planted module shadowing a Python import). The
   executable is resolved on `PATH`, i.e. it is something the operator
   installed, not a file from the target.

A target with no `.si/contracts.json` and no operator-supplied source
yields no observations at all -- never an inferred one.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind

#: Relative to a target's root, next to `.si/requirements.json`.
CONTRACTS_DECLARATION_PATH = Path(".si") / "contracts.json"
DEFAULT_CONTRACT_TIMEOUT_SECONDS = 30.0
#: A contract document is a few KB to a few hundred KB in practice; refuse
#: anything far beyond that rather than parse arbitrarily large output.
MAX_CONTRACT_BYTES = 5 * 1024 * 1024
_STDERR_TAIL_CHARS = 300

#: The only variables a contract command inherits from the caller's
#: environment: enough to find interpreters and decode text, nothing that
#: carries credentials (GITHUB_TOKEN, cloud keys, ...).
_INHERITED_ENV_KEYS = ("PATH", "SYSTEMROOT", "TZ")


@dataclass(frozen=True)
class ContractObservation:
    """One collected contract source: its parsed document, or why there is none.

    Exactly one of `document`/`error` is set. `label` is a stable,
    human-readable name for the source (a path, or the command line) used
    in Finding statements, so repeated scans compare equal (`si watch`).
    """

    kind: Literal["file", "command", "declaration"]
    label: str
    evidence: Evidence
    document: Any = None
    error: str | None = None


class _DeclaredContract(BaseModel):
    path: str


class _ContractsDeclaration(BaseModel):
    """The schema of `.si/contracts.json`."""

    contracts: list[_DeclaredContract] = Field(default_factory=list)


def _parse_json_text(text: str) -> tuple[Any, str | None]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON: {exc}"


def _file_observation(path: Path, label: str) -> ContractObservation:
    def observed(observation: str) -> Evidence:
        return Evidence(
            kind=EvidenceKind.FILE,
            source=label,
            observation=observation,
            confidence=Confidence.VERIFIED,
        )

    try:
        size = path.stat().st_size
        if size > MAX_CONTRACT_BYTES:
            error = f"larger than {MAX_CONTRACT_BYTES} bytes ({size}); not read"
            return ContractObservation("file", label, observed(error), error=error)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        error = f"could not be read: {exc.__class__.__name__}: {exc}"
        return ContractObservation("file", label, observed(error), error=error)
    document, parse_error = _parse_json_text(text)
    if parse_error is not None:
        return ContractObservation("file", label, observed(parse_error), error=parse_error)
    return ContractObservation(
        "file", label, observed("contract document read from file"), document=document
    )


def confined_path(root: Path, relative: str) -> Path | None:
    """`root / relative`, or None if it is absolute or escapes `root` (incl. via symlink)."""
    if Path(relative).is_absolute():
        return None
    resolved_root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        return None
    return candidate


def read_declared_contracts(root: Path) -> list[ContractObservation]:
    """Contracts listed in `<root>/.si/contracts.json`, if that file exists.

    A malformed declaration, or a listed path that is absolute or leaves
    the target root, is returned as an observation with `error` set rather
    than raised -- the same never-abort-the-whole-run rule every analyzer
    follows.
    """
    declaration = root / CONTRACTS_DECLARATION_PATH
    if not declaration.is_file():
        return []
    label = CONTRACTS_DECLARATION_PATH.as_posix()

    def declaration_error(error: str) -> ContractObservation:
        evidence = Evidence(
            kind=EvidenceKind.FILE, source=label, observation=error, confidence=Confidence.VERIFIED
        )
        return ContractObservation("declaration", label, evidence, error=error)

    try:
        raw = json.loads(declaration.read_text(encoding="utf-8"))
        parsed = _ContractsDeclaration.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        return [declaration_error(f"could not be parsed: {exc}")]

    observations: list[ContractObservation] = []
    for entry in parsed.contracts:
        path = confined_path(root, entry.path)
        if path is None:
            observations.append(
                declaration_error(
                    f"lists {entry.path!r}, which is absolute or outside the target root; not read"
                )
            )
            continue
        observations.append(_file_observation(path, entry.path))
    return observations


def read_contract_file(path: Path) -> ContractObservation:
    """An operator-supplied contract file (relative paths resolve against the CWD)."""
    return _file_observation(path, str(path))


def _minimal_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _INHERITED_ENV_KEYS if key in os.environ}
    env.update(
        {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_COLOR": "1",
        }
    )
    return env


def run_contract_command(
    argv: Sequence[str], timeout: float = DEFAULT_CONTRACT_TIMEOUT_SECONDS
) -> ContractObservation:
    """Run one operator-named contract command and parse its stdout as JSON.

    See the module docstring for the isolation rules. Any failure -- not
    found on PATH, timeout, non-zero exit, oversized or non-JSON stdout --
    is returned as an observation with `error` set, never raised.
    """
    label = shlex.join(argv)

    def observed(observation: str) -> Evidence:
        return Evidence(
            kind=EvidenceKind.RUNTIME_TELEMETRY,
            source=label,
            observation=observation,
            confidence=Confidence.VERIFIED,
        )

    def failed(error: str) -> ContractObservation:
        return ContractObservation("command", label, observed(error), error=error)

    if not argv:
        return failed("empty command")
    env = _minimal_env()
    executable = shutil.which(argv[0], path=env.get("PATH"))
    if executable is None:
        return failed(f"{argv[0]!r} was not found on PATH")

    try:
        with tempfile.TemporaryDirectory(prefix="si-contract-") as workdir:
            # argv list with shell=False: no shell ever parses the operator's
            # input, and the executable was resolved on PATH above.
            proc = subprocess.run(  # noqa: S603 # nosec B603
                [executable, *argv[1:]],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                cwd=workdir,
                env=env,
                shell=False,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return failed(f"timed out after {timeout:g}s")
    except OSError as exc:
        return failed(f"could not be started: {exc}")

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()[-_STDERR_TAIL_CHARS:]
        return failed(f"exited with status {proc.returncode}" + (f": {stderr}" if stderr else ""))
    if len(proc.stdout) > MAX_CONTRACT_BYTES:
        return failed(f"printed more than {MAX_CONTRACT_BYTES} bytes; not parsed")
    document, error = _parse_json_text(proc.stdout.decode("utf-8", errors="replace"))
    if error is not None:
        return failed(f"stdout is {error}")
    return ContractObservation(
        "command", label, observed("contract document printed on stdout"), document=document
    )


def collect_contracts(
    root: Path,
    contract_files: Sequence[Path] = (),
    contract_commands: Sequence[Sequence[str]] = (),
    timeout: float = DEFAULT_CONTRACT_TIMEOUT_SECONDS,
) -> list[ContractObservation]:
    """Every contract source for a target, static sources first (ADR-011)."""
    return [
        *read_declared_contracts(root),
        *(read_contract_file(path) for path in contract_files),
        *(run_contract_command(argv, timeout) for argv in contract_commands),
    ]

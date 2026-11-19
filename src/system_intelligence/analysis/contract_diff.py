"""Contract diff: is a change to a capability contract additive or breaking? (ADR-019)

Two saved contracts of one component, the one a dependent may already
rely on (`old`) and the proposed one (`new`), are compared key by key.
Every difference is one change with an effect:

- `breaking`: a caller written against `old` may fail against `new`
  (something removed, a type or value changed, a field newly required,
  a guarantee weakened);
- `additive`: everything `old` offered is still there and something was
  added (a key, an operation, an enum value, an entry), or a field is no
  longer required, or a guarantee was strengthened;
- `info`: documentation and metadata that callers do not program
  against (descriptions, the release version, lifecycle promotion).

The whole diff is `breaking` when any change is, else `additive` when
any change is, else `none`. The recommended release bump follows from
it and from the old release version (`version`, else `skill.version`):
before 1.0, breaking is a minor bump and additive a patch bump (a caret
range `^0.y.z` accepts patches only); from 1.0, breaking is major and
additive minor. `none` recommends no bump.

The rules know nothing about one skill: they read the JSON structure
and a few key names every contract in the ecosystem uses the same way
(`required`, `lifecycle`, `description`, ...). What a change means in
prose (a parameter that keeps its name but changes its meaning) is not
seen; the diff is as good as the contract is explicit. The report has no
ids or timestamps; changes are sorted, so the same inputs give the same
JSON.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

REPORT_FORMAT = "system-intelligence/contract-diff@1"

Effect = Literal["breaking", "additive", "info"]
Classification = Literal["none", "additive", "breaking"]
Bump = Literal["none", "patch", "minor", "major"]
ObservedBump = Literal["none", "patch", "minor", "major", "downgrade", "unknown"]

EFFECTS: tuple[Effect, ...] = ("breaking", "additive", "info")
_BUMP_RANK: dict[str, int] = {"none": 0, "patch": 1, "minor": 2, "major": 3}

# Keys whose whole subtree is documentation: any change below them is `info`.
INFORMATIONAL_KEYS = frozenset(
    {
        "$comment",
        "comment",
        "description",
        "doc",
        "docs",
        "examples",
        "help",
        "not_provided",
        "note",
        "notes",
        "summary",
        "title",
    }
)
# Top-level keys (and `skill.<key>`) that describe the release, not the shape.
RELEASE_KEYS = frozenset({"version", "contract_version"})
IDENTITY_KEYS = frozenset({"skill_id", "id"})
# Arrays whose order is meaning (an argv): any change is breaking.
ORDERED_KEYS = frozenset({"argv", "canonical_invocation", "command", "invocation"})
# Boolean guarantees and the value that is the stronger promise to a caller.
GUARANTEES: dict[str, bool] = {
    "arbitrary_executables": False,
    "arbitrary_filters": False,
    "canonical_json": True,
    "deterministic": True,
    "deterministic_inputs": True,
    "input_mutation": False,
    "mutates_input": False,
    "network": False,
    "shell": False,
}
# Booleans saying whether a caller must give something: `False` is the looser one.
REQUIREMENT_FLAGS: dict[str, bool] = {"required": False, "optional": True}
LIFECYCLE_ORDER = ("PROPOSED", "EXPERIMENTAL", "STABLE", "DEPRECATED", "RETIRED")
# Field names that identify an entry of an array of objects, in order of preference.
ENTRY_KEYS = ("id", "tool_id", "skill_id", "code", "name", "key", "artifact_id", "kind")

_VERSION = re.compile(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?")
_SHOWN = 160
_MISSING: Any = object()


class ContractChange(BaseModel):
    """One difference. `pointer` is a JSON Pointer into `new`, or into `old` for a removal."""

    model_config = ConfigDict(frozen=True)

    pointer: str
    effect: Effect
    rule: str
    detail: str
    old: str | None = None
    new: str | None = None


class VersionPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    old: str | None
    new: str | None


class ContractDiffReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str = REPORT_FORMAT
    old_source: str
    new_source: str
    classification: Classification
    recommended_bump: Bump
    next_version: str | None = Field(
        default=None, description="The old release version with the recommended bump applied."
    )
    version: VersionPair
    observed_bump: ObservedBump = Field(
        description="How the release version itself moved between old and new."
    )
    bump_sufficient: bool | None = Field(
        default=None,
        description="Whether the observed bump is at least the recommended one; null when the "
        "version did not move (the release is not part of this diff).",
    )
    contract_version: VersionPair
    summary: dict[str, int]
    changes: list[ContractChange]
    notes: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


class ContractReadError(ValueError):
    """A contract that cannot be read, or a git ref or path that does not resolve."""


def _escape(token: str | int) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _join(pointer: str, token: str | int) -> str:
    return f"{pointer}/{_escape(token)}"


def _shown(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text if len(text) <= _SHOWN else text[: _SHOWN - 3] + "..."


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_key(old: list[Any], new: list[Any]) -> str | None:
    """The field that names every object entry of both arrays uniquely, if there is one."""
    items = old + new
    if not items or not all(isinstance(item, Mapping) for item in items):
        return None
    for field in ENTRY_KEYS:
        if not all(
            isinstance(item.get(field), str | int) and not isinstance(item.get(field), bool)
            for item in items
        ):
            continue
        if all(len({_canonical(i[field]) for i in side}) == len(side) for side in (old, new)):
            return field
    return None


class _Differ:
    def __init__(self, release: tuple[str | None, str | None] = (None, None)) -> None:
        self.changes: list[ContractChange] = []
        # The release versions of both sides: a nested `version` that repeats them is metadata.
        self.release = release

    def add(
        self,
        pointer: str,
        effect: Effect,
        rule: str,
        detail: str,
        old: Any = _MISSING,
        new: Any = _MISSING,
    ) -> None:
        self.changes.append(
            ContractChange(
                pointer=pointer or "/",
                effect=effect,
                rule=rule,
                detail=detail,
                old=None if old is _MISSING else _shown(old),
                new=None if new is _MISSING else _shown(new),
            )
        )

    # -- dispatch ---------------------------------------------------------------

    def value(self, pointer: str, key: str | None, old: Any, new: Any, info: bool) -> None:
        if _canonical(old) == _canonical(new):
            return
        if info:
            self.add(pointer, "info", "documentation", "documentation changed", old, new)
            return
        if _kind(old) != _kind(new):
            self.add(
                pointer,
                "breaking",
                "type-changed",
                f"type changed from {_kind(old)} to {_kind(new)}",
                old,
                new,
            )
            return
        if isinstance(old, Mapping):
            self.mapping(pointer, old, new)
        elif isinstance(old, list):
            self.array(pointer, key, old, new)
        else:
            self.scalar(pointer, key, old, new)

    def mapping(self, pointer: str, old: Mapping[str, Any], new: Mapping[str, Any]) -> None:
        for key in sorted(set(old) | set(new)):
            here = _join(pointer, key)
            info = key in INFORMATIONAL_KEYS
            if key not in new:
                if info:
                    self.add(here, "info", "documentation", "documentation removed", old[key])
                elif key == "required" and isinstance(old[key], list):
                    for item in old[key]:
                        self.add(
                            here,
                            "additive",
                            "required-removed",
                            f"{_shown(item)} is no longer required",
                            item,
                        )
                else:
                    self.add(here, "breaking", "key-removed", f"{key!r} removed", old[key])
            elif key not in old:
                if info:
                    self.add(here, "info", "documentation", "documentation added", new=new[key])
                elif key == "required" and isinstance(new[key], list):
                    for item in new[key]:
                        self.add(
                            here,
                            "breaking",
                            "required-added",
                            f"{_shown(item)} is now required",
                            new=item,
                        )
                elif key in REQUIREMENT_FLAGS and new[key] is not REQUIREMENT_FLAGS[key]:
                    self.add(
                        here,
                        "breaking",
                        "required-flag",
                        f"{key!r} set to {_shown(new[key])}",
                        new=new[key],
                    )
                else:
                    self.add(here, "additive", "key-added", f"{key!r} added", new=new[key])
            else:
                self.value(here, key, old[key], new[key], info)

    def array(self, pointer: str, key: str | None, old: list[Any], new: list[Any]) -> None:
        if key in ORDERED_KEYS:
            self.add(
                pointer,
                "breaking",
                "ordered-changed",
                f"{key!r} is an ordered list and changed",
                old,
                new,
            )
            return
        field = _entry_key(old, new)
        if field is not None:
            old_by = {_canonical(item[field]): (i, item) for i, item in enumerate(old)}
            new_by = {_canonical(item[field]): (i, item) for i, item in enumerate(new)}
            for name, (index, item) in old_by.items():
                if name not in new_by:
                    self.add(
                        _join(pointer, index),
                        "breaking",
                        "entry-removed",
                        f"entry {field}={_shown(item[field])} removed",
                        item,
                    )
            for name, (index, item) in new_by.items():
                if name not in old_by:
                    self.add(
                        _join(pointer, index),
                        "additive",
                        "entry-added",
                        f"entry {field}={_shown(item[field])} added",
                        new=item,
                    )
                else:
                    self.value(_join(pointer, index), None, old_by[name][1], item, False)
            return
        old_items = {_canonical(item): (i, item) for i, item in enumerate(old)}
        new_items = {_canonical(item): (i, item) for i, item in enumerate(new)}
        required = key == "required"
        for text, (index, item) in old_items.items():
            if text not in new_items:
                if required:
                    self.add(
                        _join(pointer, index),
                        "additive",
                        "required-removed",
                        f"{_shown(item)} is no longer required",
                        item,
                    )
                else:
                    self.add(
                        _join(pointer, index),
                        "breaking",
                        "item-removed",
                        f"{_shown(item)} removed",
                        item,
                    )
        for text, (index, item) in new_items.items():
            if text not in old_items:
                if required:
                    self.add(
                        _join(pointer, index),
                        "breaking",
                        "required-added",
                        f"{_shown(item)} is now required",
                        new=item,
                    )
                else:
                    self.add(
                        _join(pointer, index),
                        "additive",
                        "item-added",
                        f"{_shown(item)} added",
                        new=item,
                    )

    def scalar(self, pointer: str, key: str | None, old: Any, new: Any) -> None:
        if old == new:
            return
        if key == "version" and None not in self.release and (old, new) == self.release:
            self.add(pointer, "info", "release-version", "the release version, repeated", old, new)
            return
        if key in GUARANTEES and isinstance(old, bool):
            stronger = GUARANTEES[key]
            if new is stronger:
                self.add(
                    pointer,
                    "additive",
                    "guarantee-strengthened",
                    f"{key!r} now promises {_shown(new)}",
                    old,
                    new,
                )
            else:
                self.add(
                    pointer,
                    "breaking",
                    "guarantee-weakened",
                    f"{key!r} no longer promises {_shown(old)}",
                    old,
                    new,
                )
            return
        if key in REQUIREMENT_FLAGS and isinstance(old, bool):
            if new is REQUIREMENT_FLAGS[key]:
                self.add(
                    pointer,
                    "additive",
                    "required-flag",
                    f"no longer required ({key!r} {_shown(old)} -> {_shown(new)})",
                    old,
                    new,
                )
            else:
                self.add(
                    pointer,
                    "breaking",
                    "required-flag",
                    f"now required ({key!r} {_shown(old)} -> {_shown(new)})",
                    old,
                    new,
                )
            return
        if key == "lifecycle" and old in LIFECYCLE_ORDER and new in LIFECYCLE_ORDER:
            before, after = LIFECYCLE_ORDER.index(old), LIFECYCLE_ORDER.index(new)
            if after < before or new == "RETIRED":
                self.add(
                    pointer,
                    "breaking",
                    "lifecycle-regressed",
                    f"lifecycle {old} -> {new}",
                    old,
                    new,
                )
            else:
                self.add(
                    pointer, "info", "lifecycle-promoted", f"lifecycle {old} -> {new}", old, new
                )
            return
        rule = "default-changed" if key == "default" else "value-changed"
        what = "default" if key == "default" else "value"
        self.add(pointer, "breaking", rule, f"{what} changed", old, new)


def _release_version(document: Any) -> str | None:
    if not isinstance(document, Mapping):
        return None
    value = document.get("version")
    skill = document.get("skill")
    if value is None and isinstance(skill, Mapping):
        value = skill.get("version")
    return value if isinstance(value, str) else None


def _contract_version(document: Any) -> str | None:
    if not isinstance(document, Mapping):
        return None
    value = document.get("contract_version")
    if value is None or isinstance(value, bool):
        return None
    return str(value)


def _parse(version: str | None) -> tuple[int, int, int] | None:
    match = _VERSION.match(version or "")
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def recommend_bump(classification: Classification, old_version: str | None) -> Bump:
    """The bump ADR-019 recommends for a classification, from the old release version."""
    if classification == "none":
        return "none"
    parsed = _parse(old_version)
    pre_one = parsed is not None and parsed[0] == 0
    if classification == "breaking":
        return "minor" if pre_one else "major"
    return "patch" if pre_one else "minor"


def bumped(version: str | None, bump: Bump) -> str | None:
    parsed = _parse(version)
    if parsed is None or bump == "none":
        return None
    major, minor, patch = parsed
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def observed_bump(old: str | None, new: str | None) -> ObservedBump:
    a, b = _parse(old), _parse(new)
    if a is None or b is None:
        return "none" if old == new else "unknown"
    if a == b:
        return "none"
    if b < a:
        return "downgrade"
    if b[0] != a[0]:
        return "major"
    return "minor" if b[1] != a[1] else "patch"


def _top_level(differ: _Differ, old: Mapping[str, Any], new: Mapping[str, Any]) -> None:
    """Release keys and identity at the top (and under `skill`), then the rest by the rules."""
    rest_old = dict(old)
    rest_new = dict(new)
    for key in sorted(RELEASE_KEYS):
        a, b = rest_old.pop(key, None), rest_new.pop(key, None)
        if _canonical(a) != _canonical(b):
            differ.add(
                _join("", key),
                "info",
                "release-version",
                f"{key} {a} -> {b}",
                old.get(key, _MISSING),
                new.get(key, _MISSING),
            )
    skill_old, skill_new = rest_old.get("skill"), rest_new.get("skill")
    if isinstance(skill_old, Mapping) and isinstance(skill_new, Mapping):
        skill_old, skill_new = dict(skill_old), dict(skill_new)
        a, b = skill_old.pop("version", None), skill_new.pop("version", None)
        if _canonical(a) != _canonical(b):
            differ.add(
                "/skill/version",
                "info",
                "release-version",
                f"version {a} -> {b}",
                old["skill"].get("version", _MISSING),
                new["skill"].get("version", _MISSING),
            )
        rest_old["skill"], rest_new["skill"] = skill_old, skill_new
    for key in sorted(IDENTITY_KEYS):
        if key in rest_old and key in rest_new and rest_old[key] != rest_new[key]:
            differ.add(
                _join("", key),
                "breaking",
                "identity-changed",
                f"{key} changed: a dependent resolves this contract by it",
                rest_old[key],
                rest_new[key],
            )
            del rest_old[key], rest_new[key]
    differ.mapping("", rest_old, rest_new)


def diff_contracts(
    old: Any,
    new: Any,
    *,
    old_source: str = "old",
    new_source: str = "new",
) -> ContractDiffReport:
    """Every difference between two contracts, its effect, and the bump the result needs.

    `old` or `new` may be `None`: the contract did not exist on that side
    (added: additive; removed: breaking).
    """
    differ = _Differ((_release_version(old), _release_version(new)))
    notes: list[str] = []
    if old is None and new is None:
        raise ContractReadError("neither side has a contract")
    if old is None:
        differ.add("/", "additive", "contract-added", "contract added", new=new)
    elif new is None:
        differ.add("/", "breaking", "contract-removed", "contract removed", old)
    elif isinstance(old, Mapping) and isinstance(new, Mapping):
        _top_level(differ, old, new)
    else:
        differ.value("", None, old, new, False)

    changes = sorted(
        differ.changes, key=lambda c: (EFFECTS.index(c.effect), c.pointer, c.rule, c.detail)
    )
    summary: dict[str, int] = {
        effect: sum(1 for c in changes if c.effect == effect) for effect in EFFECTS
    }
    classification: Classification = (
        "breaking" if summary["breaking"] else "additive" if summary["additive"] else "none"
    )
    old_version, new_version = _release_version(old), _release_version(new)
    # A new contract has no old version: its own tells whether it is before 1.0.
    basis = old_version if old is not None else new_version
    bump = recommend_bump(classification, basis)
    observed = observed_bump(old_version, new_version)
    sufficient = None if observed == "none" else _BUMP_RANK.get(observed, -1) >= _BUMP_RANK[bump]
    if observed in ("downgrade", "unknown"):
        sufficient = False
    if old is None or new is None:
        observed, sufficient = "unknown", None
    if bump != "none" and _parse(basis) is None:
        notes.append(
            f"the release version ({basis!r}) is not N.N[.N]; the 1.0-and-later rules were used"
        )
    old_cv, new_cv = _contract_version(old), _contract_version(new)
    if classification == "breaking" and old is not None and new is not None and old_cv == new_cv:
        notes.append(
            f"breaking changes with contract_version unchanged ({old_cv}); a dependent pinned "
            "to that contract_version would accept this contract"
        )
    if classification != "breaking" and old_cv != new_cv and old is not None and new is not None:
        notes.append(f"contract_version moved ({old_cv} -> {new_cv}) without a breaking change")
    return ContractDiffReport(
        old_source=old_source,
        new_source=new_source,
        classification=classification,
        recommended_bump=bump,
        next_version=bumped(old_version, bump) if old is not None else None,
        version=VersionPair(old=old_version, new=new_version),
        observed_bump=observed,
        bump_sufficient=sufficient,
        contract_version=VersionPair(old=old_cv, new=new_cv),
        summary=summary,
        changes=changes,
        notes=notes,
    )


# -- reading ------------------------------------------------------------------


def parse_contract_text(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractReadError(f"{source}: not JSON ({exc})") from exc


def read_contract_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractReadError(f"{path}: {exc}") from exc
    return parse_contract_text(text, str(path))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise ContractReadError("git is not on PATH")
    # Fixed argv, no shell; the ref and path were checked not to be options.
    return subprocess.run(  # nosec B603
        [git, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def read_contract_at_ref(repo: Path, ref: str, path: str) -> Any | None:
    """The contract at `path` in commit `ref` of the repository at `repo`; `None` if absent there.

    A ref that is not a commit is an error, not an absent contract.
    """
    if not ref or ref.startswith("-") or not path or path.startswith("-"):
        raise ContractReadError(f"refused ref {ref!r} or path {path!r}")
    verified = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if verified.returncode != 0:
        raise ContractReadError(f"{ref!r} is not a commit in {repo}")
    commit = verified.stdout.strip()
    spec = f"{commit}:{path.lstrip('/')}"
    if _git(repo, "cat-file", "-e", spec).returncode != 0:
        return None
    try:
        shown = _git(repo, "cat-file", "blob", spec)
    except UnicodeDecodeError as exc:
        raise ContractReadError(f"{ref}:{path}: not UTF-8") from exc
    if shown.returncode != 0:
        raise ContractReadError(f"{ref}:{path}: {shown.stderr.strip()}")
    return parse_contract_text(shown.stdout, f"{ref}:{path}")


# -- output -------------------------------------------------------------------


def _cell(text: str | None) -> str:
    if text is None:
        return "-"
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def format_diff_table(report: ContractDiffReport) -> str:
    """The verdict and bump, then one row per change, breaking first."""
    counts = report.summary
    bump: str = report.recommended_bump
    if bump != "none" and report.next_version:
        bump += f" ({report.version.old} -> {report.next_version})"
    lines = [
        f"Contract diff: {report.classification}; recommended bump: {bump}; "
        f"{counts['breaking']} breaking, {counts['additive']} additive, {counts['info']} info "
        f"({report.old_source} -> {report.new_source})",
    ]
    if report.changes:
        lines += [
            "",
            "| Effect | Pointer | Change | Old | New | Rule |",
            "|---|---|---|---|---|---|",
        ]
        for change in report.changes:
            lines.append(
                f"| {change.effect} | `{_cell(change.pointer)}` | {_cell(change.detail)} | "
                f"{_cell(change.old)} | {_cell(change.new)} | {change.rule} |"
            )
    notes = [f"- {note}" for note in report.notes]
    if report.observed_bump != "none":
        verdict = {True: "enough", False: "not enough", None: "n/a"}[report.bump_sufficient]
        notes.append(
            f"- the release version moved {report.version.old} -> {report.version.new} "
            f"({report.observed_bump}): {verdict} for {report.recommended_bump}"
        )
    if notes:
        lines += ["", "Notes:", *notes]
    return "\n".join(lines) + "\n"

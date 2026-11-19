import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from system_intelligence.analysis.contract_diff import (
    ContractDiffReport,
    ContractReadError,
    bumped,
    diff_contracts,
    format_diff_table,
    observed_bump,
    read_contract_at_ref,
    recommend_bump,
)

BASE: dict[str, Any] = {
    "skill_id": "alpha",
    "version": "0.4.0",
    "contract_version": "1",
    "description": "Measures things.",
    "deterministic": True,
    "operations": ["inspect", "check"],
    "statuses": ["PASS", "FAIL"],
    "execution": {"canonical_invocation": ["alpha", "run", "-"], "network": False},
    "provides": [
        {"id": "measure.a", "lifecycle": "EXPERIMENTAL", "tool_id": "alpha/check"},
        {"id": "measure.b", "lifecycle": "STABLE", "tool_id": "alpha/check"},
    ],
    "tools": [{"tool_id": "alpha/check", "version": "0.4.0", "produces": ["checks"]}],
    "inputs": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "default": 3}},
        "required": ["path"],
    },
    "rules": {"max_gap": {"type": "Optional[float]", "default": None, "required": False}},
    "not_provided": ["editing"],
}


def _diff(change: Any) -> ContractDiffReport:
    new = copy.deepcopy(BASE)
    change(new)
    return diff_contracts(BASE, new)


def _rules(report: ContractDiffReport) -> list[tuple[str, str, str]]:
    return [(c.effect, c.rule, c.pointer) for c in report.changes]


def test_identical_contracts_are_none_and_need_no_bump() -> None:
    report = diff_contracts(BASE, copy.deepcopy(BASE))

    assert report.classification == "none"
    assert report.recommended_bump == "none"
    assert report.changes == [] and report.next_version is None
    assert report.summary == {"breaking": 0, "additive": 0, "info": 0}


def test_order_of_a_set_like_array_and_of_keys_is_not_a_change() -> None:
    new = copy.deepcopy(BASE)
    new["operations"] = ["check", "inspect"]
    new["provides"] = list(reversed(new["provides"]))
    reordered = dict(reversed(list(new.items())))

    assert diff_contracts(BASE, reordered).changes == []


def test_an_added_operation_is_additive_a_patch_before_one() -> None:
    report = _diff(lambda d: d["operations"].append("validate"))

    assert _rules(report) == [("additive", "item-added", "/operations/2")]
    assert report.classification == "additive"
    assert report.recommended_bump == "patch"
    assert report.next_version == "0.4.1"


def test_a_removed_operation_is_breaking_a_minor_before_one() -> None:
    report = _diff(lambda d: d["operations"].remove("check"))

    assert _rules(report) == [("breaking", "item-removed", "/operations/1")]
    assert report.changes[0].old == '"check"'
    assert report.recommended_bump == "minor"
    assert report.next_version == "0.5.0"


def test_from_one_breaking_is_major_and_additive_minor() -> None:
    old = copy.deepcopy(BASE)
    old["version"] = "1.4.1"
    removed = copy.deepcopy(old)
    removed["statuses"] = ["PASS"]
    added = copy.deepcopy(old)
    added["statuses"].append("WARN")

    assert diff_contracts(old, removed).recommended_bump == "major"
    assert diff_contracts(old, removed).next_version == "2.0.0"
    assert diff_contracts(old, added).recommended_bump == "minor"
    assert diff_contracts(old, added).next_version == "1.5.0"


def test_an_enum_value_added_is_additive_and_removed_is_breaking() -> None:
    assert _diff(lambda d: d["statuses"].append("UNKNOWN")).classification == "additive"
    assert _diff(lambda d: d["statuses"].remove("FAIL")).classification == "breaking"


def test_a_new_key_is_additive_and_a_removed_key_breaking() -> None:
    added = _diff(lambda d: d["inputs"]["properties"].update({"mode": {"type": "string"}}))
    removed = _diff(lambda d: d["inputs"]["properties"].pop("limit"))

    assert _rules(added) == [("additive", "key-added", "/inputs/properties/mode")]
    assert _rules(removed) == [("breaking", "key-removed", "/inputs/properties/limit")]


def test_an_entry_of_a_keyed_array_is_matched_by_its_identity() -> None:
    added = _diff(
        lambda d: d["provides"].insert(
            0, {"id": "measure.c", "lifecycle": "PROPOSED", "tool_id": "alpha/check"}
        )
    )
    removed = _diff(lambda d: d["provides"].pop(0))
    changed = _diff(lambda d: d["provides"][1].update({"tool_id": "alpha/run"}))

    assert _rules(added) == [("additive", "entry-added", "/provides/0")]
    assert 'id="measure.c"' in added.changes[0].detail
    assert _rules(removed) == [("breaking", "entry-removed", "/provides/0")]
    assert _rules(changed) == [("breaking", "value-changed", "/provides/1/tool_id")]


def test_making_a_field_required_is_breaking_and_dropping_it_additive() -> None:
    required = _diff(lambda d: d["inputs"]["required"].append("limit"))
    relaxed = _diff(lambda d: d["inputs"].update({"required": []}))
    no_list = _diff(lambda d: d["inputs"].pop("required"))

    assert _rules(required) == [("breaking", "required-added", "/inputs/required/1")]
    assert _rules(relaxed) == [("additive", "required-removed", "/inputs/required/0")]
    assert _rules(no_list) == [("additive", "required-removed", "/inputs/required")]


def test_a_new_required_list_is_breaking() -> None:
    report = _diff(lambda d: d["rules"].update({"required": ["max_gap"]}))

    assert _rules(report) == [("breaking", "required-added", "/rules/required")]


def test_a_required_flag_turned_on_is_breaking_and_off_additive() -> None:
    on = _diff(lambda d: d["rules"]["max_gap"].update({"required": True}))
    new_flag = _diff(lambda d: d["inputs"]["properties"]["path"].update({"required": True}))
    optional_off = _diff(lambda d: d["inputs"]["properties"]["path"].update({"optional": False}))
    old = copy.deepcopy(BASE)
    old["rules"]["max_gap"]["required"] = True
    off = diff_contracts(old, BASE)

    assert _rules(on) == [("breaking", "required-flag", "/rules/max_gap/required")]
    assert new_flag.classification == "breaking"
    assert optional_off.classification == "breaking"
    assert _rules(off) == [("additive", "required-flag", "/rules/max_gap/required")]


def test_a_type_change_is_breaking() -> None:
    to_object = _diff(lambda d: d.update({"operations": {"inspect": {}}}))
    type_text = _diff(lambda d: d["rules"]["max_gap"].update({"type": "float"}))

    assert _rules(to_object) == [("breaking", "type-changed", "/operations")]
    assert "from array to object" in to_object.changes[0].detail
    assert _rules(type_text) == [("breaking", "value-changed", "/rules/max_gap/type")]


def test_a_changed_default_is_breaking() -> None:
    report = _diff(lambda d: d["inputs"]["properties"]["limit"].update({"default": 5}))

    assert _rules(report) == [("breaking", "default-changed", "/inputs/properties/limit/default")]


def test_an_integer_and_the_same_float_are_equal() -> None:
    assert (
        _diff(lambda d: d["inputs"]["properties"]["limit"].update({"default": 3.0})).changes == []
    )


def test_a_guarantee_weakened_is_breaking_and_strengthened_additive() -> None:
    weakened = _diff(lambda d: d.update({"deterministic": False}))
    network = _diff(lambda d: d["execution"].update({"network": True}))
    old = copy.deepcopy(BASE)
    old["execution"]["network"] = True
    strengthened = diff_contracts(old, BASE)

    assert _rules(weakened) == [("breaking", "guarantee-weakened", "/deterministic")]
    assert _rules(network) == [("breaking", "guarantee-weakened", "/execution/network")]
    assert _rules(strengthened) == [("additive", "guarantee-strengthened", "/execution/network")]


def test_an_ordered_list_is_compared_in_order() -> None:
    report = _diff(lambda d: d["execution"].update({"canonical_invocation": ["alpha", "-", "run"]}))
    added = _diff(lambda d: d["execution"]["canonical_invocation"].append("--json"))

    assert _rules(report) == [("breaking", "ordered-changed", "/execution/canonical_invocation")]
    assert added.classification == "breaking"


def test_lifecycle_promotion_is_info_and_regression_or_retirement_breaking() -> None:
    promoted = _diff(lambda d: d["provides"][0].update({"lifecycle": "STABLE"}))
    deprecated = _diff(lambda d: d["provides"][1].update({"lifecycle": "DEPRECATED"}))
    regressed = _diff(lambda d: d["provides"][1].update({"lifecycle": "EXPERIMENTAL"}))
    retired = _diff(lambda d: d["provides"][1].update({"lifecycle": "RETIRED"}))

    assert _rules(promoted) == [("info", "lifecycle-promoted", "/provides/0/lifecycle")]
    assert promoted.classification == "none"
    assert deprecated.classification == "none"
    assert _rules(regressed) == [("breaking", "lifecycle-regressed", "/provides/1/lifecycle")]
    assert retired.classification == "breaking"


def test_documentation_is_info_whatever_changes_inside_it() -> None:
    report = _diff(
        lambda d: d.update(
            {"description": {"text": "now an object"}, "not_provided": ["editing", "repair"]}
        )
    )
    added = _diff(lambda d: d["inputs"]["properties"]["path"].update({"description": "a path"}))

    assert {c.effect for c in report.changes} == {"info"}
    assert report.classification == "none"
    assert _rules(added) == [("info", "documentation", "/inputs/properties/path/description")]


def test_the_release_version_anywhere_is_info() -> None:
    def release(d: dict[str, Any]) -> None:
        d["version"] = "0.4.1"
        d["tools"][0]["version"] = "0.4.1"

    report = _diff(release)

    assert _rules(report) == [
        ("info", "release-version", "/tools/0/version"),
        ("info", "release-version", "/version"),
    ]
    assert report.classification == "none"
    assert report.observed_bump == "patch"
    assert report.bump_sufficient is True


def test_a_nested_version_that_is_not_the_release_is_a_value() -> None:
    report = _diff(lambda d: d["tools"][0].update({"version": "9.9.9"}))

    assert _rules(report) == [("breaking", "value-changed", "/tools/0/version")]


def test_skill_version_is_the_release_when_there_is_no_top_level_version() -> None:
    old = {"skill": {"id": "engine", "version": "1.2.0"}, "contract_version": "1.0", "ops": ["a"]}
    new = copy.deepcopy(old)
    new["skill"]["version"] = "1.3.0"
    new["ops"].append("b")

    report = diff_contracts(old, new)

    assert _rules(report) == [
        ("additive", "item-added", "/ops/1"),
        ("info", "release-version", "/skill/version"),
    ]
    assert report.version.old == "1.2.0" and report.recommended_bump == "minor"
    assert report.observed_bump == "minor" and report.bump_sufficient is True


def test_a_changed_identity_is_breaking() -> None:
    report = _diff(lambda d: d.update({"skill_id": "beta"}))

    assert _rules(report) == [("breaking", "identity-changed", "/skill_id")]


def test_breaking_with_the_same_contract_version_is_noted() -> None:
    report = _diff(lambda d: d["operations"].remove("check"))
    moved = _diff(lambda d: d.update({"contract_version": "2"}))

    assert any("contract_version unchanged (1)" in note for note in report.notes)
    assert moved.classification == "none"
    assert _rules(moved) == [("info", "release-version", "/contract_version")]
    assert any("moved (1 -> 2) without a breaking change" in note for note in moved.notes)


def test_an_added_or_removed_contract() -> None:
    added = diff_contracts(None, BASE)
    removed = diff_contracts(BASE, None)

    assert _rules(added) == [("additive", "contract-added", "/")]
    assert added.recommended_bump == "patch" and added.next_version is None
    assert _rules(removed) == [("breaking", "contract-removed", "/")]
    assert removed.recommended_bump == "minor"
    assert removed.observed_bump == "unknown" and removed.bump_sufficient is None
    with pytest.raises(ContractReadError):
        diff_contracts(None, None)


def test_changes_are_sorted_breaking_first_and_the_report_is_deterministic() -> None:
    def many(d: dict[str, Any]) -> None:
        d["operations"].append("validate")
        d["statuses"].remove("FAIL")
        d["description"] = "Changed."

    first, second = _diff(many), _diff(many)

    assert [c.effect for c in first.changes] == ["breaking", "additive", "info"]
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json())["format"] == "system-intelligence/contract-diff@1"


def test_long_values_are_shortened() -> None:
    report = _diff(lambda d: d.update({"blob": "x" * 500}))

    assert report.changes[0].new is not None
    assert len(report.changes[0].new) == 160 and report.changes[0].new.endswith("...")


def test_pointer_tokens_are_escaped() -> None:
    report = _diff(lambda d: d.update({"a/b~c": 1}))

    assert report.changes[0].pointer == "/a~1b~0c"


@pytest.mark.parametrize(
    ("classification", "version", "bump"),
    [
        ("none", "0.1.0", "none"),
        ("additive", "0.1.0", "patch"),
        ("breaking", "0.1.0", "minor"),
        ("additive", "1.0.0", "minor"),
        ("breaking", "2.3.4", "major"),
        ("breaking", None, "major"),
        ("additive", "v0.9", "patch"),
    ],
)
def test_recommend_bump(classification: Any, version: str | None, bump: str) -> None:
    assert recommend_bump(classification, version) == bump


def test_an_unreadable_version_uses_the_one_point_oh_rules_and_says_so() -> None:
    old = copy.deepcopy(BASE)
    old["version"] = "next"
    new = copy.deepcopy(old)
    new["operations"].append("validate")

    report = diff_contracts(old, new)

    assert report.recommended_bump == "minor" and report.next_version is None
    assert any("is not N.N[.N]" in note for note in report.notes)


@pytest.mark.parametrize(
    ("old", "new", "observed"),
    [
        ("0.4.0", "0.4.0", "none"),
        ("0.4.0", "0.4.1", "patch"),
        ("0.4.0", "0.5.0", "minor"),
        ("0.4.0", "1.0.0", "major"),
        ("0.4.0", "0.3.9", "downgrade"),
        ("0.4.0", "next", "unknown"),
        (None, None, "none"),
    ],
)
def test_observed_bump(old: str | None, new: str | None, observed: str) -> None:
    assert observed_bump(old, new) == observed


def test_bumped() -> None:
    assert bumped("0.4.2", "patch") == "0.4.3"
    assert bumped("0.4.2", "minor") == "0.5.0"
    assert bumped("1.4", "major") == "2.0.0"
    assert bumped("0.4.2", "none") is None and bumped("x", "minor") is None


def test_an_insufficient_bump_is_reported() -> None:
    def change(d: dict[str, Any]) -> None:
        d["operations"].remove("check")
        d["version"] = "0.4.1"

    report = _diff(change)

    assert report.recommended_bump == "minor"
    assert report.observed_bump == "patch" and report.bump_sufficient is False
    assert "(patch): not enough for minor" in format_diff_table(report)


def test_the_table_lists_every_change_and_escapes_cells() -> None:
    report = _diff(lambda d: d["operations"].append("a|b"))
    table = format_diff_table(report)

    assert table.startswith(
        "Contract diff: additive; recommended bump: patch (0.4.0 -> 0.4.1); "
        "0 breaking, 1 additive, 0 info (old -> new)"
    )
    assert '| additive | `/operations/2` | "a\\|b" added | - | "a\\|b" | item-added |' in table


def test_the_table_of_an_empty_diff_is_one_line() -> None:
    assert format_diff_table(diff_contracts(BASE, BASE)).count("\n") == 1


# -- git ----------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git is not installed")
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "contract.json").write_text(json.dumps(BASE), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_read_contract_at_ref(repo: Path) -> None:
    assert read_contract_at_ref(repo, "main", "contract/contract.json") == BASE
    assert read_contract_at_ref(repo, "HEAD", "/contract/contract.json") == BASE
    assert read_contract_at_ref(repo, "main", "contract/missing.json") is None


@pytest.mark.parametrize(("ref", "path"), [("-x", "a.json"), ("main", "--output=x"), ("", "a")])
def test_read_contract_at_ref_refuses_options(repo: Path, ref: str, path: str) -> None:
    with pytest.raises(ContractReadError, match="refused"):
        read_contract_at_ref(repo, ref, path)


def test_read_contract_at_ref_refuses_an_unknown_ref_and_bad_json(repo: Path) -> None:
    with pytest.raises(ContractReadError, match="is not a commit"):
        read_contract_at_ref(repo, "no-such-branch", "contract/contract.json")
    (repo / "bad.json").write_text("{", encoding="utf-8")
    _git(repo, "add", "bad.json")
    _git(repo, "commit", "-q", "-m", "bad")
    with pytest.raises(ContractReadError, match="not JSON"):
        read_contract_at_ref(repo, "HEAD", "bad.json")


def test_null_to_a_value_is_a_type_change() -> None:
    report = _diff(lambda d: d["rules"]["max_gap"].update({"default": 0.5}))

    assert _rules(report) == [("breaking", "type-changed", "/rules/max_gap/default")]
    assert "from null to number" in report.changes[0].detail


def test_removed_documentation_is_info() -> None:
    report = _diff(lambda d: d.pop("description"))

    assert _rules(report) == [("info", "documentation", "/description")]


def test_objects_without_a_unique_identity_are_compared_whole() -> None:
    old = {"version": "0.1.0", "rows": [{"id": "a", "n": 1}, {"id": "a", "n": 2}]}
    new = {"version": "0.1.0", "rows": [{"id": "a", "n": 1}, {"id": "a", "n": 3}]}

    report = diff_contracts(old, new)

    assert _rules(report) == [
        ("breaking", "item-removed", "/rows/1"),
        ("additive", "item-added", "/rows/1"),
    ]


def test_contracts_that_are_not_objects_are_compared_as_values() -> None:
    assert _rules(diff_contracts([1], [1, 2])) == [("additive", "item-added", "/1")]
    assert diff_contracts([1], {"a": 1}).classification == "breaking"

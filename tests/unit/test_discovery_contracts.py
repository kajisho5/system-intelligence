import json
import os
import sys
from pathlib import Path

import pytest

from system_intelligence.core.evidence import EvidenceKind
from system_intelligence.discovery import contracts
from system_intelligence.discovery.contracts import (
    collect_contracts,
    read_contract_file,
    read_declared_contracts,
    run_contract_command,
)


def _declare(root: Path, paths: list[str]) -> None:
    (root / ".si").mkdir(exist_ok=True)
    (root / ".si" / "contracts.json").write_text(
        json.dumps({"contracts": [{"path": p} for p in paths]}), encoding="utf-8"
    )


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_no_declaration_means_no_observations(tmp_path: Path) -> None:
    assert read_declared_contracts(tmp_path) == []
    assert collect_contracts(tmp_path) == []


def test_declared_contract_is_read(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text('{"skill_id": "x"}', encoding="utf-8")
    _declare(tmp_path, ["contract.json"])

    [observation] = read_declared_contracts(tmp_path)

    assert observation.kind == "file"
    assert observation.label == "contract.json"
    assert observation.document == {"skill_id": "x"}
    assert observation.error is None
    assert observation.evidence.kind == EvidenceKind.FILE


@pytest.mark.parametrize("path", ["/etc/hostname", "../outside.json", "sub/../../outside.json"])
def test_declared_path_outside_root_is_refused(tmp_path: Path, path: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    _declare(root, [path])

    [observation] = read_declared_contracts(root)

    assert observation.document is None
    assert observation.error is not None and "outside the target root" in observation.error


def test_declared_symlink_escaping_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
    (root / "contract.json").symlink_to(tmp_path / "secret.json")
    _declare(root, ["contract.json"])

    [observation] = read_declared_contracts(root)

    assert observation.error is not None and "outside the target root" in observation.error


def test_malformed_declaration_is_an_observation_not_an_exception(tmp_path: Path) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "contracts.json").write_text('{"contracts": "nope"}', encoding="utf-8")

    [observation] = read_declared_contracts(tmp_path)

    assert observation.kind == "declaration"
    assert observation.label == ".si/contracts.json"
    assert observation.error is not None and "could not be parsed" in observation.error


def test_declaration_cannot_name_a_command(tmp_path: Path) -> None:
    """A checked-in file must never make System Intelligence run anything."""
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "contracts.json").write_text(
        '{"contracts": [{"command": "touch pwned"}]}', encoding="utf-8"
    )

    [observation] = read_declared_contracts(tmp_path)

    assert observation.error is not None
    assert not (tmp_path / "pwned").exists()


def test_contract_file_missing_or_not_json(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")

    missing = read_contract_file(tmp_path / "missing.json")
    bad = read_contract_file(tmp_path / "bad.json")

    assert missing.error is not None and "could not be read" in missing.error
    assert bad.error is not None and "not valid JSON" in bad.error


def test_oversized_contract_file_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contracts, "MAX_CONTRACT_BYTES", 4)
    (tmp_path / "big.json").write_text('{"skill_id": "x"}', encoding="utf-8")

    observation = read_contract_file(tmp_path / "big.json")

    assert observation.error is not None and "not read" in observation.error


def test_command_stdout_is_parsed() -> None:
    observation = run_contract_command(_python('print(\'{"skill_id": "x"}\')'))

    assert observation.kind == "command"
    assert observation.document == {"skill_id": "x"}
    assert observation.evidence.kind == EvidenceKind.RUNTIME_TELEMETRY
    assert observation.label.startswith(sys.executable)


def test_command_gets_a_minimal_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "should-not-leak")
    monkeypatch.setenv("HOME", "/somewhere")

    observation = run_contract_command(
        _python("import json, os; print(json.dumps(sorted(os.environ)))")
    )

    assert observation.error is None
    assert "GITHUB_TOKEN" not in observation.document
    assert "HOME" not in observation.document
    assert "PATH" in observation.document


def test_command_runs_in_an_empty_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "planted.txt").write_text("x", encoding="utf-8")

    observation = run_contract_command(
        _python("import json, os; print(json.dumps([os.getcwd(), os.listdir('.')]))")
    )

    cwd, listing = observation.document
    assert Path(cwd).resolve() != tmp_path.resolve()
    assert listing == []
    assert not Path(cwd).exists()  # cleaned up afterwards


def test_command_arguments_never_reach_a_shell(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"

    observation = run_contract_command(
        _python("import json, sys; print(json.dumps(sys.argv[1:]))") + [f"; touch {marker}"]
    )

    assert observation.document == [f"; touch {marker}"]
    assert not marker.exists()


def test_command_not_on_path() -> None:
    observation = run_contract_command(["si-no-such-command-xyz", "contract", "--json"])

    assert observation.error is not None and "not found on PATH" in observation.error


def test_command_non_zero_exit_reports_stderr_tail() -> None:
    observation = run_contract_command(_python("import sys; sys.stderr.write('boom'); sys.exit(3)"))

    assert observation.error == "exited with status 3: boom"


def test_command_non_json_stdout() -> None:
    observation = run_contract_command(_python("print('hello')"))

    assert observation.error is not None and observation.error.startswith("stdout is not valid")


def test_command_timeout() -> None:
    observation = run_contract_command(_python("import time; time.sleep(5)"), timeout=0.5)

    assert observation.error == "timed out after 0.5s"


def test_empty_command() -> None:
    assert run_contract_command([]).error == "empty command"


def test_collect_contracts_orders_static_sources_first(tmp_path: Path) -> None:
    (tmp_path / "declared.json").write_text("{}", encoding="utf-8")
    _declare(tmp_path, ["declared.json"])
    given = tmp_path / "given.json"
    given.write_text("{}", encoding="utf-8")

    observations = collect_contracts(tmp_path, [given], [_python("print('{}')")])

    assert [o.kind for o in observations] == ["file", "file", "command"]
    assert os.path.basename(observations[1].label) == "given.json"

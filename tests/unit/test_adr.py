from pathlib import Path

from system_intelligence.discovery.adr import detect_adrs


def test_detect_adrs_parses_number_status_and_title(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-003-agent-os-boundary.md").write_text(
        "# ADR-003: The OS/Agent Boundary Is a Dependency Direction\n\n"
        "Status: Accepted\n\n## Context\n\nSome context.\n",
        encoding="utf-8",
    )

    adrs = detect_adrs(tmp_path)

    assert len(adrs) == 1
    adr = adrs[0]
    assert adr.number == 3
    assert adr.status == "Accepted"
    assert adr.name == "The OS/Agent Boundary Is a Dependency Direction"
    assert adr.path == "docs/adr/ADR-003-agent-os-boundary.md"
    assert adr.decided_at is None
    assert adr.evidence


def test_detect_adrs_missing_status_stays_none_not_fabricated(tmp_path: Path) -> None:
    (tmp_path / "ADR-1-no-status.md").write_text("# ADR-1: No status line\n", encoding="utf-8")

    adrs = detect_adrs(tmp_path)

    assert len(adrs) == 1
    assert adrs[0].status is None
    assert adrs[0].number == 1


def test_detect_adrs_missing_heading_falls_back_to_filename_stem(tmp_path: Path) -> None:
    (tmp_path / "ADR-7-plain.md").write_text(
        "Status: Proposed\nNo heading here.\n", encoding="utf-8"
    )

    adrs = detect_adrs(tmp_path)

    assert len(adrs) == 1
    assert adrs[0].name == "ADR-7-plain"


def test_detect_adrs_ignores_non_matching_filenames(tmp_path: Path) -> None:
    (tmp_path / "0001-bare-numeric.md").write_text("Status: Accepted\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")

    assert detect_adrs(tmp_path) == []


def test_detect_adrs_none_found(tmp_path: Path) -> None:
    assert detect_adrs(tmp_path) == []


def test_detect_adrs_ignores_vendored_dirs(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "some-pkg" / "docs" / "adr"
    vendored.mkdir(parents=True)
    (vendored / "ADR-1-vendored.md").write_text("Status: Accepted\n", encoding="utf-8")

    assert detect_adrs(tmp_path) == []


def test_detect_adrs_is_case_insensitive_and_sorted_by_path(tmp_path: Path) -> None:
    (tmp_path / "adr-2-second.md").write_text("Status: Accepted\n", encoding="utf-8")
    (tmp_path / "ADR-1-first.md").write_text("Status: Accepted\n", encoding="utf-8")

    adrs = detect_adrs(tmp_path)

    assert [a.path for a in adrs] == ["ADR-1-first.md", "adr-2-second.md"]

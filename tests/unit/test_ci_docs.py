from pathlib import Path

from system_intelligence.discovery.ci_docs import (
    detect_ci_jobs,
    detect_license,
    detect_root_documents,
)


def test_detect_ci_jobs(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    jobs = detect_ci_jobs(tmp_path)

    assert len(jobs) == 1
    assert jobs[0].provider == "github-actions"
    assert jobs[0].workflow_path == ".github/workflows/ci.yml"


def test_detect_ci_jobs_none(tmp_path: Path) -> None:
    assert detect_ci_jobs(tmp_path) == []


def test_detect_root_documents(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")

    documents = detect_root_documents(tmp_path)

    document_types = {d.document_type for d in documents}
    assert document_types == {"README", "LICENSE"}


def test_detect_root_documents_is_case_insensitive(tmp_path: Path) -> None:
    """A case-sensitive filesystem must not report a real readme/license as
    missing just because its case differs from the canonical spelling --
    GitHub's own README/LICENSE detection doesn't require exact case either."""
    (tmp_path / "readme.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "License").write_text("MIT\n", encoding="utf-8")

    documents = detect_root_documents(tmp_path)

    document_types = {d.document_type for d in documents}
    assert document_types == {"README", "LICENSE"}
    # The actual on-disk name/path is preserved, not the canonical spelling.
    names = {d.name for d in documents}
    assert names == {"readme.md", "License"}


def test_detect_root_documents_recognizes_bare_and_txt_variants(tmp_path: Path) -> None:
    (tmp_path / "README").write_text("Hello\n", encoding="utf-8")
    (tmp_path / "LICENSE.txt").write_text("MIT\n", encoding="utf-8")

    documents = detect_root_documents(tmp_path)

    document_types = {d.document_type for d in documents}
    assert document_types == {"README", "LICENSE"}


def test_detect_root_documents_recognizes_code_of_conduct(tmp_path: Path) -> None:
    """CODE_OF_CONDUCT.md is one of GitHub's own community health file
    conventions, the same family CONTRIBUTING/SECURITY are already drawn
    from -- recorded when present, same as SECURITY.md."""
    (tmp_path / "CODE_OF_CONDUCT.md").write_text("# Code of Conduct\n", encoding="utf-8")

    documents = detect_root_documents(tmp_path)

    document_types = {d.document_type for d in documents}
    assert document_types == {"CODE_OF_CONDUCT"}


def test_detect_root_documents_none_present(tmp_path: Path) -> None:
    assert detect_root_documents(tmp_path) == []


def test_detect_root_documents_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert detect_root_documents(tmp_path / "does-not-exist") == []


def test_detect_license_mit(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2026 Example\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy of this "
        'software and associated documentation files (the "Software"), to deal in the Software '
        "without restriction.\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "MIT"


def test_detect_license_apache_2_0(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "Apache-2.0"


def test_detect_license_gpl_3_0(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n", encoding="utf-8"
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "GPL-3.0"


def test_detect_license_gpl_2_0(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991\n", encoding="utf-8"
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "GPL-2.0"


def test_detect_license_bsd_3_clause(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Redistribution and use in source and binary forms, with or without modification, "
        "are permitted provided that the following conditions are met:\n\n"
        "1. Redistributions of source code must retain the above copyright notice.\n"
        "2. Redistributions in binary form must reproduce the above copyright notice.\n"
        "3. Neither the name of the copyright holder nor the names of its contributors "
        "may be used to endorse or promote products derived from this software.\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "BSD-3-Clause"


def test_detect_license_bsd_2_clause_without_third_clause(tmp_path: Path) -> None:
    """A real BSD-2-Clause file has only the first two clauses (no
    "Neither the name of..." endorsement clause) -- must not be
    misclassified as BSD-3-Clause just because the substrings overlap."""
    (tmp_path / "LICENSE").write_text(
        "Redistribution and use in source and binary forms, with or without modification, "
        "are permitted provided that the following conditions are met:\n\n"
        "1. Redistributions of source code must retain the above copyright notice.\n"
        "2. Redistributions in binary form must reproduce the above copyright notice.\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "BSD-2-Clause"


def test_detect_license_isc(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "ISC License\n\nCopyright (c) 2026 Example\n\n"
        "Permission to use, copy, modify, and/or distribute this software for any "
        "purpose with or without fee is hereby granted.\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "ISC"


def test_detect_license_unlicense(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "This is free and unencumbered software released into the public domain.\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "Unlicense"


def test_detect_license_mpl_2_0(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Mozilla Public License Version 2.0\n==================================\n",
        encoding="utf-8",
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) == "MPL-2.0"


def test_detect_license_unrecognized_text_returns_none(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "All rights reserved. No license granted.\n", encoding="utf-8"
    )
    documents = detect_root_documents(tmp_path)

    assert detect_license(tmp_path, documents) is None


def test_detect_license_no_license_document_returns_none(tmp_path: Path) -> None:
    assert detect_license(tmp_path, []) is None

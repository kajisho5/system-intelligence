"""ChangePlan: a pure, side-effect-free description of a local change.

Matches the "plan/preview" half of the execution adapter SDK
(docs/design/docs/18-extension-points.md). Building a `ChangePlan` never
touches the filesystem or git — only `local_git.apply_plan` does, and only
after a policy check passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from system_intelligence.core.enums import PermissionLevel


@dataclass(frozen=True)
class ChangePlan:
    branch_name: str
    commit_message: str
    files: dict[str, str]  # path relative to repo root -> new file content
    required_permission_level: PermissionLevel = PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR
    description: str = ""
    evidence_summary: list[str] = field(default_factory=list)

    def preview_lines(self) -> list[str]:
        """Human-readable preview — what `local_git.apply_plan` would do, without doing it."""
        lines = [
            f"Create local branch {self.branch_name!r}",
            f"Write {len(self.files)} file(s): {', '.join(sorted(self.files))}",
            f"Commit with message: {self.commit_message!r}",
        ]
        if self.description:
            lines.insert(0, self.description)
        return lines

    def to_plan_file_dict(self) -> dict[str, object]:
        """Serialize to the exact shape `cli/main.py`'s `execute` command reads back.

        `required_permission_level` is written by name (`"CREATE_BRANCH_OR_
        DRAFT_PR"`), not by int value — `execute` looks it up via
        `PermissionLevel[name]`, matching how a hand-authored plan file
        already writes it.
        """
        return {
            "branch_name": self.branch_name,
            "commit_message": self.commit_message,
            "files": self.files,
            "description": self.description,
            "evidence_summary": self.evidence_summary,
            "required_permission_level": self.required_permission_level.name,
        }

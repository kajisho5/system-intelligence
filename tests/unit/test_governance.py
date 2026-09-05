import pytest
from pydantic import ValidationError

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval


def test_approval_allows_draft_pr_creation() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="kajisho5/system-intelligence",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    assert approval.action == "create_draft_pr"


@pytest.mark.parametrize(
    "forbidden_action",
    [
        "merge_pull_request",
        "delete_repository",
        "force_push",
        "rotate_credentials",
    ],
)
def test_approval_rejects_forbidden_actions(forbidden_action: str) -> None:
    with pytest.raises(ValidationError, match="forbidden by default"):
        Approval(
            actor="human:kajisho5",
            scope="repository",
            action=forbidden_action,
            target="kajisho5/system-intelligence",
            permission_level=PermissionLevel.MODIFY_REMOTE_REPOSITORY,
        )

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval, AuditLogEntry


def test_approval_allows_draft_pr_creation() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="kajisho5/system-intelligence",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    assert approval.action == "create_draft_pr"


def test_approval_approved_at_is_timezone_aware_and_comparable() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="kajisho5/system-intelligence",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    assert approval.approved_at.tzinfo is not None
    # Must not raise "can't compare offset-naive and offset-aware datetimes".
    assert approval.approved_at <= datetime.now(UTC)


def test_audit_log_entry_timestamp_is_timezone_aware() -> None:
    entry = AuditLogEntry(
        actor="human:kajisho5",
        intent="diagnose",
        target="kajisho5/system-intelligence",
        action="scan",
        result="ok",
        correlation_id="corr-1",
    )
    assert entry.timestamp.tzinfo is not None


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

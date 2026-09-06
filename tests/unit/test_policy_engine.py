from datetime import UTC, datetime, timedelta

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval
from system_intelligence.policy.engine import evaluate


def test_forbidden_action_always_denied_even_with_no_approvals_needed() -> None:
    decision = evaluate("merge_pull_request", "owner/repo", PermissionLevel.OBSERVE)
    assert decision.allowed is False
    assert "forbidden by default" in decision.reason


def test_default_level_allowed_without_approval() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)
    assert decision.allowed is True


def test_above_default_level_denied_without_approval() -> None:
    decision = evaluate("create_draft_pr", "owner/repo", PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR)
    assert decision.allowed is False
    assert "no matching approval" in decision.reason


def test_above_default_level_allowed_with_matching_approval() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    decision = evaluate(
        "create_draft_pr",
        "owner/repo",
        PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        approvals=[approval],
    )
    assert decision.allowed is True
    assert approval.id in decision.reason


def test_approval_for_different_action_does_not_cover() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    decision = evaluate(
        "create_local_branch",
        "owner/repo",
        PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        approvals=[approval],
    )
    assert decision.allowed is False


def test_approval_for_different_target_does_not_cover() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo-a",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    decision = evaluate(
        "create_draft_pr",
        "owner/repo-b",
        PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        approvals=[approval],
    )
    assert decision.allowed is False


def test_approval_at_lower_level_than_required_does_not_cover() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
    decision = evaluate(
        "create_draft_pr",
        "owner/repo",
        PermissionLevel.MODIFY_REMOTE_REPOSITORY,
        approvals=[approval],
    )
    assert decision.allowed is False


def test_expired_approval_does_not_cover() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    decision = evaluate(
        "create_draft_pr",
        "owner/repo",
        PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        approvals=[approval],
    )
    assert decision.allowed is False


def test_unexpired_approval_with_future_expiry_covers() -> None:
    approval = Approval(
        actor="human:kajisho5",
        scope="repository",
        action="create_draft_pr",
        target="owner/repo",
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    decision = evaluate(
        "create_draft_pr",
        "owner/repo",
        PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        approvals=[approval],
    )
    assert decision.allowed is True

from datetime import UTC, datetime, timedelta

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval
from system_intelligence.policy.engine import audit_log_entry, evaluate


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


def test_audit_log_entry_records_allowed_decision_with_its_policy_reason() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(
        decision, action="generate_report", target="owner/repo", intent="produce a report"
    )

    assert entry.result == "allowed"
    assert entry.policy == decision.reason
    assert entry.action == "generate_report"
    assert entry.target == "owner/repo"
    assert entry.intent == "produce a report"


def test_audit_log_entry_records_denied_decision() -> None:
    decision = evaluate("create_draft_pr", "owner/repo", PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR)

    entry = audit_log_entry(
        decision, action="create_draft_pr", target="owner/repo", intent="ship a fix"
    )

    assert entry.result == "denied"


def test_audit_log_entry_defaults_actor_to_system_cli_without_fabricating_a_human() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(decision, action="generate_report", target="owner/repo", intent="x")

    assert entry.actor == "system:cli"


def test_audit_log_entry_uses_explicit_actor_when_given() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(
        decision, action="generate_report", target="owner/repo", intent="x", actor="human:kajisho5"
    )

    assert entry.actor == "human:kajisho5"


def test_audit_log_entry_evidence_ids_empty_by_default_not_fabricated() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(decision, action="generate_report", target="owner/repo", intent="x")

    assert entry.evidence_ids == []


def test_audit_log_entry_correlation_id_defaults_when_not_given() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(decision, action="generate_report", target="owner/repo", intent="x")

    assert entry.correlation_id
    assert entry.correlation_id.startswith("correlation-")


def test_audit_log_entry_correlation_id_uses_explicit_value_when_given() -> None:
    decision = evaluate("generate_report", "owner/repo", PermissionLevel.GENERATE_LOCAL_ARTIFACTS)

    entry = audit_log_entry(
        decision,
        action="generate_report",
        target="owner/repo",
        intent="x",
        correlation_id="abc123def456",
    )

    assert entry.correlation_id == "abc123def456"

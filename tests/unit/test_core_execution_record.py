from system_intelligence.core.execution_record import ExecutionRecord


def test_execution_record_defaults() -> None:
    record = ExecutionRecord(
        action="create_local_branch_and_commit",
        target="/repo",
        applied=False,
        decision_reason="denied: no matching approval",
    )
    assert record.branch_name is None
    assert record.commit_sha is None
    assert record.files_written == []
    assert record.executed_at.tzinfo is not None

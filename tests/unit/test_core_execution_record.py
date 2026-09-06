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
    assert record.pull_request_number is None
    assert record.pull_request_url is None
    assert record.executed_at.tzinfo is not None


def test_execution_record_records_a_pull_request() -> None:
    record = ExecutionRecord(
        action="create_draft_pr",
        target="o/r",
        applied=True,
        decision_reason="Approved by 'human:test' (approval abc)",
        pull_request_number=7,
        pull_request_url="https://github.com/o/r/pull/7",
    )
    assert record.pull_request_number == 7
    assert record.pull_request_url == "https://github.com/o/r/pull/7"

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
import os
from pathlib import Path

from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus, TelemetryRecord
from models.root_cause import CodeCandidate
from services.root_cause_analysis import CodeSearchAdapter, GitHistoryAdapter, RootCauseAnalyzer
from shared.types.telemetry import Environment


def build_incident() -> IncidentRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fingerprint-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="billing-api: Database timeout in checkout flow",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.CRITICAL,
        first_seen_at=now,
        last_seen_at=now,
        event_count=1,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )


def build_event() -> IncidentEventRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return IncidentEventRecord(
        id="event-1",
        incident_id="incident-1",
        telemetry_id="telemetry-1",
        event_type="telemetry.received",
        error_message='Database timeout while calling fetch_invoice in billing_client.py',
        stacktrace='Traceback (most recent call last):\n  File "services/billing_client.py", line 18, in fetch_invoice\n    raise TimeoutError("database timeout")',
        request_payload={"method": "POST", "url": "/checkout"},
        response_payload={"status_code": 503},
        payload={"environment": "production"},
        occurred_at=now,
        created_at=now,
    )


def build_classification() -> FailureClassification:
    return FailureClassification(
        category=FailureCategory.DATABASE_FAILURE,
        confidence=0.89,
        summary="The billing-api incident is most likely a database failure based on database, timeout.",
        matched_signals=["database", "timeout"],
        inspected_event_count=1,
    )


def build_latest_telemetry() -> TelemetryRecord:
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    return TelemetryRecord(
        id="telemetry-1",
        project_id="project-1",
        environment=Environment.PRODUCTION,
        service="billing-api",
        error_message="Database timeout while calling fetch_invoice",
        stacktrace='File "services/billing_client.py", line 18, in fetch_invoice',
        fingerprint="fingerprint-1",
        request_payload={"method": "POST"},
        response_payload={"status_code": 503},
        commit_sha="deadbeef",
        occurred_at=now,
        received_at=now,
    )


def test_root_cause_analyzer_ranks_code_candidates_from_stack_trace(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_file = repo_root / "services" / "billing_client.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        """
def fetch_invoice(invoice_id: str) -> dict:
    raise TimeoutError("database timeout")
""".strip(),
        encoding="utf-8",
    )

    unrelated_file = repo_root / "client-ui" / "src" / "app.ts"
    unrelated_file.parent.mkdir(parents=True)
    unrelated_file.write_text("export const noop = () => null;\n", encoding="utf-8")

    analyzer = RootCauseAnalyzer(
        code_search=CodeSearchAdapter(repo_root),
        git_history=GitHistoryAdapter(repo_root),
    )

    evidence = analyzer.analyze(
        incident=build_incident(),
        events=[build_event()],
        classification=build_classification(),
        latest_telemetry=build_latest_telemetry(),
    )

    assert evidence.code_candidates
    assert evidence.code_candidates[0].file_path == "services/billing_client.py"
    assert evidence.code_snippets
    assert evidence.code_snippets[0].file_path == "services/billing_client.py"
    assert "def fetch_invoice" in evidence.code_snippets[0].content
    assert evidence.suspected_component == "services/billing_client.py"
    assert "billing_client.py" in evidence.stack_trace_signals
    assert evidence.latest_commit_sha == "deadbeef"


def test_git_history_adapter_returns_recent_commits_for_candidate_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    file_path = repo_root / "services" / "billing_client.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("def fetch_invoice():\n    return {}\n", encoding="utf-8")

    env = {
        "GIT_AUTHOR_NAME": "Cursor Test",
        "GIT_AUTHOR_EMAIL": "cursor@example.com",
        "GIT_COMMITTER_NAME": "Cursor Test",
        "GIT_COMMITTER_EMAIL": "cursor@example.com",
    }
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "Add billing client"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )

    adapter = GitHistoryAdapter(repo_root)
    candidate = [
        CodeCandidate(
            file_path="services/billing_client.py",
            symbol="fetch_invoice",
            match_reason="stack trace file match",
            matched_terms=["billing_client.py"],
            confidence=0.85,
        )
    ]

    signals = adapter.inspect(code_candidates=candidate, latest_commit_sha=None)

    assert signals
    assert signals[0].file_path == "services/billing_client.py"
    assert signals[0].commit_summary == "Add billing client"

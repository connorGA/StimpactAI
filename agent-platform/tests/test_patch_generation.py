from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.core.errors import APIError
from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus, TelemetryRecord
from services.code_context import CodeContextService
from services.patch_generation import PatchGenerationService, summarize_unified_diff
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
        error_message="Database timeout while calling fetch_invoice in billing_client.py",
        stacktrace='Traceback (most recent call last):\n  File "services/billing_client.py", line 18, in fetch_invoice',
        request_payload={"method": "POST"},
        response_payload={"status_code": 503},
        payload={"environment": "production"},
        occurred_at=now,
        created_at=now,
    )


def build_telemetry() -> TelemetryRecord:
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


class StubIncidentRepository:
    def __init__(self) -> None:
        self.incident = build_incident()
        self.events = [build_event()]
        self.telemetry = build_telemetry()

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        return self.incident if incident_id == self.incident.id else None

    async def list_incident_events(
        self,
        incident_id: str,
        *,
        limit: int = 100,
    ) -> list[IncidentEventRecord]:
        assert incident_id == self.incident.id
        return self.events[:limit]

    async def get_telemetry(self, telemetry_id: str) -> TelemetryRecord:
        assert telemetry_id == self.telemetry.id
        return self.telemetry


class StubPatchRepository:
    def __init__(self) -> None:
        self.created = []

    async def get_latest_patch_run(self, incident_id: str):
        assert incident_id == "incident-1"
        return None

    async def create_patch_run(self, **kwargs):
        self.created.append(kwargs)
        proposal = kwargs["proposal"]
        now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
        return SimpleNamespace(
            id="patch-1",
            incident_id=kwargs["incident_id"],
            status="generated",
            patch_summary=proposal.patch_summary,
            rationale=proposal.rationale,
            target_files=proposal.target_files,
            unified_diff=proposal.unified_diff,
            verification_steps=proposal.verification_steps,
            confidence=proposal.confidence,
            model_name=kwargs["model_name"],
            based_on_commit_sha=kwargs["based_on_commit_sha"],
            diff_line_count=kwargs["diff_line_count"],
            file_count=kwargs["file_count"],
            created_at=now,
            updated_at=now,
        )


class StubFailureClassifier:
    def classify(self, incident: IncidentRecord, events: list[IncidentEventRecord]) -> FailureClassification:
        assert incident.id == "incident-1"
        assert len(events) == 1
        return FailureClassification(
            category=FailureCategory.DATABASE_FAILURE,
            confidence=0.91,
            summary="The billing-api incident is most likely a database failure.",
            matched_signals=["database", "timeout"],
            inspected_event_count=1,
        )


class StubCodeContextService:
    def build_evidence(self, **kwargs):
        return SimpleNamespace(
            latest_commit_sha="deadbeef",
            model_dump=lambda mode="json": {
                "suspected_component": "services/billing_client.py",
                "evidence_summary": "Code evidence points at the billing client timeout path.",
                "stack_trace_signals": ["billing_client.py", "fetch_invoice"],
                "search_terms": ["database", "timeout", "fetch_invoice"],
                "code_candidates": [
                    {
                        "file_path": "services/billing_client.py",
                        "symbol": "fetch_invoice",
                        "match_reason": "stack trace file match",
                        "matched_terms": ["billing_client.py", "fetch_invoice"],
                        "confidence": 0.88,
                    }
                ],
                "code_snippets": [
                    {
                        "file_path": "services/billing_client.py",
                        "symbol": "fetch_invoice",
                        "start_line": 1,
                        "end_line": 4,
                        "content": "def fetch_invoice():\n    raise TimeoutError('database timeout')",
                        "match_reason": "stack trace file match",
                        "confidence": 0.88,
                    }
                ],
                "git_signals": [],
                "evidence_confidence": 0.78,
                "latest_commit_sha": "deadbeef",
                "inspected_event_count": 1,
            },
        )


class RecordingOpenAIClient:
    def __init__(self, payload: dict[str, object]) -> None:
        content = json.dumps(payload)
        self.chat = SimpleNamespace(completions=_RecordingCompletions(content))


class _RecordingCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    async def create(self, **kwargs: object) -> object:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_summarize_unified_diff_counts_files_and_changed_lines() -> None:
    summary = summarize_unified_diff(
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    assert summary.file_count == 1
    assert summary.changed_line_count == 2


@pytest.mark.asyncio
async def test_patch_generation_rejects_large_diffs() -> None:
    large_diff = "\n".join(
        [
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1,0 +1,201 @@",
            *[f"+line_{index}" for index in range(201)],
        ]
    )
    service = PatchGenerationService(
        StubIncidentRepository(),
        StubPatchRepository(),
        classifier=StubFailureClassifier(),
        code_context=StubCodeContextService(),
        client=RecordingOpenAIClient(
            {
                "patch_summary": "Too large patch",
                "rationale": "Testing the validator.",
                "target_files": [{"path": "a.py", "reason": "Test file"}],
                "unified_diff": large_diff,
                "verification_steps": ["Run tests"],
                "confidence": 0.55,
            }
        ),
        model="patch-model",
    )

    with pytest.raises(APIError) as exc_info:
        await service.get_or_generate_patch("incident-1", event_limit=20)

    assert exc_info.value.code == "patch_constraints_violated"

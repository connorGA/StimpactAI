from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.schemas.chat import ChatMessage, IncidentDetailChatRequest
from models.failure_classification import FailureCategory, FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, IncidentSeverity, IncidentStatus, TelemetryRecord
from services.code_context import CodeContextService, CodeSearchAdapter, GitHistoryAdapter, SnippetRetriever
from services.incident_chat import IncidentChatService
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


class StubFailureClassifier:
    def classify(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        return self._result(incident, events)

    async def classify_async(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        return self._result(incident, events)

    def _result(
        self,
        incident: IncidentRecord,
        events: list[IncidentEventRecord],
    ) -> FailureClassification:
        assert incident.id == "incident-1"
        assert len(events) == 1
        return FailureClassification(
            category=FailureCategory.DATABASE_FAILURE,
            confidence=0.91,
            summary="The billing-api incident is most likely a database failure based on database and timeout.",
            matched_signals=["database", "timeout"],
            inspected_event_count=1,
        )


class RecordingOpenAIClient:
    def __init__(self, answer: str) -> None:
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(completions=_RecordingCompletions(self.calls, answer))


class _RecordingCompletions:
    def __init__(self, calls: list[dict[str, object]], answer: str) -> None:
        self._calls = calls
        self._answer = answer

    async def create(self, **kwargs: object) -> object:
        self._calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._answer),
                )
            ]
        )


@pytest.mark.asyncio
async def test_incident_chat_includes_retrieved_code_context_in_prompt(tmp_path: Path) -> None:
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

    client = RecordingOpenAIClient("The billing client timeout path looks suspect.")
    service = IncidentChatService(
        StubIncidentRepository(),
        client=client,
        model="test-model",
        classifier=StubFailureClassifier(),
        code_context=CodeContextService(
            code_search=CodeSearchAdapter(repo_root),
            snippet_retriever=SnippetRetriever(repo_root),
            git_history=GitHistoryAdapter(repo_root),
        ),
    )

    response = await service.chat_about_incident(
        "incident-1",
        IncidentDetailChatRequest(
            messages=[ChatMessage(role="user", content="What code path looks suspect?")],
            event_limit=25,
        ),
    )

    assert response.answer == "The billing client timeout path looks suspect."
    assert response.referenced_incident_ids == ["incident-1"]

    prompt_messages = client.calls[0]["messages"]
    assert isinstance(prompt_messages, list)
    context_message = prompt_messages[1]
    assert isinstance(context_message, dict)
    context = context_message["content"]
    assert isinstance(context, str)
    assert "Retrieved code context:" in context
    assert "Top code candidates:" in context
    assert "Relevant code snippets:" in context
    assert "services/billing_client.py" in context
    assert "def fetch_invoice" in context
    assert "Add billing client" in context

from __future__ import annotations

from typing import Iterable

from openai import AsyncOpenAI

from api.core.errors import APIError
from api.repositories.incident_repository import IncidentRepository
from api.schemas.chat import ChatMessage, GlobalIncidentChatRequest, IncidentChatResponse, IncidentDetailChatRequest
from services.code_context import CodeContextService
from services.failure_classifier import FailureClassifier


class IncidentChatService:
    def __init__(
        self,
        repository: IncidentRepository,
        *,
        client: AsyncOpenAI,
        model: str,
        classifier: FailureClassifier | None = None,
        code_context: CodeContextService | None = None,
    ) -> None:
        self._repository = repository
        self._client = client
        self._model = model
        self._classifier = classifier or FailureClassifier()
        self._code_context = code_context or CodeContextService()

    async def chat_about_incidents(self, request: GlobalIncidentChatRequest) -> IncidentChatResponse:
        incidents, _ = await self._repository.list_incidents(
            project_id=request.project_id,
            status=request.status.value if request.status is not None else None,
            limit=request.incident_limit,
            offset=0,
        )

        if not incidents:
            raise APIError(
                "No incidents were found for the requested chat context.",
                status_code=404,
                code="incident_chat_context_not_found",
            )

        context = "\n".join(
            [
                "Incident summaries:",
                *[
                    (
                        f"- id={incident.id} service={incident.service} env={incident.environment.value} "
                        f"severity={incident.severity.value} status={incident.status.value} "
                        f"count={incident.event_count} last_seen={incident.last_seen_at.isoformat()} "
                        f"title={incident.title}"
                    )
                    for incident in incidents
                ],
            ]
        )

        answer = await self._generate_answer(
            messages=request.messages,
            context=context,
            scope_description="a global view of current incidents",
        )
        return IncidentChatResponse(
            answer=answer,
            referenced_incident_ids=[incident.id for incident in incidents],
        )

    async def chat_about_incident(
        self,
        incident_id: str,
        request: IncidentDetailChatRequest,
    ) -> IncidentChatResponse:
        incident = await self._repository.get_incident(incident_id)
        if incident is None:
            raise APIError(
                f"Incident {incident_id} was not found.",
                status_code=404,
                code="incident_not_found",
            )

        events = await self._repository.list_incident_events(incident_id, limit=request.event_limit)
        latest_telemetry = await self._repository.get_telemetry(incident.latest_telemetry_id)
        classification = await self._classifier.classify_async(incident, events)
        evidence = self._code_context.build_evidence(
            incident=incident,
            events=events,
            classification=classification,
            latest_telemetry=latest_telemetry,
        )
        event_lines = [
            (
                f"- telemetry_id={event.telemetry_id} type={event.event_type} occurred_at={event.occurred_at.isoformat()} "
                f"error={event.error_message}\n"
                f"  stacktrace={_truncate(event.stacktrace, 1200)}\n"
                f"  request={_truncate(repr(event.request_payload), 600)}\n"
                f"  response={_truncate(repr(event.response_payload), 600)}"
            )
            for event in events
        ]
        context = "\n".join(
            [
                (
                    f"Incident detail:\n"
                    f"id={incident.id}\n"
                    f"title={incident.title}\n"
                    f"service={incident.service}\n"
                    f"environment={incident.environment.value}\n"
                    f"severity={incident.severity.value}\n"
                    f"status={incident.status.value}\n"
                    f"event_count={incident.event_count}\n"
                    f"first_seen_at={incident.first_seen_at.isoformat()}\n"
                    f"last_seen_at={incident.last_seen_at.isoformat()}\n"
                    f"fingerprint={incident.fingerprint}"
                ),
                (
                    f"Deterministic classification:\n"
                    f"category={classification.category.value}\n"
                    f"confidence={classification.confidence}\n"
                    f"summary={classification.summary}\n"
                    f"matched_signals={classification.matched_signals}"
                ),
                (
                    f"Retrieved code context:\n"
                    f"suspected_component={evidence.suspected_component}\n"
                    f"evidence_summary={evidence.evidence_summary}\n"
                    f"evidence_confidence={evidence.evidence_confidence}\n"
                    f"stack_trace_signals={evidence.stack_trace_signals}\n"
                    f"search_terms={evidence.search_terms}\n"
                    f"latest_commit_sha={evidence.latest_commit_sha}"
                ),
                "Top code candidates:",
                *[
                    (
                        f"- file={candidate.file_path} symbol={candidate.symbol} "
                        f"confidence={candidate.confidence} reason={candidate.match_reason} "
                        f"matched_terms={candidate.matched_terms}"
                    )
                    for candidate in evidence.code_candidates
                ],
                "Relevant code snippets:",
                *[
                    (
                        f"--- snippet file={snippet.file_path} lines={snippet.start_line}-{snippet.end_line} "
                        f"symbol={snippet.symbol} confidence={snippet.confidence} reason={snippet.match_reason}\n"
                        f"{snippet.content}"
                    )
                    for snippet in evidence.code_snippets
                ],
                "Relevant git history:",
                *[
                    (
                        f"- file={signal.file_path} commit={signal.commit_sha[:12]} "
                        f"summary={signal.commit_summary} reason={signal.relevance_reason}"
                    )
                    for signal in evidence.git_signals
                ],
                "Recent incident events:",
                *event_lines,
            ]
        )

        answer = await self._generate_answer(
            messages=request.messages,
            context=context,
            scope_description=f"incident {incident.id}",
        )
        return IncidentChatResponse(
            answer=answer,
            referenced_incident_ids=[incident.id],
        )

    async def _generate_answer(
        self,
        *,
        messages: Iterable[ChatMessage],
        context: str,
        scope_description: str,
    ) -> str:
        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an incident analysis assistant for a self-healing software platform. "
                        "Answer using only the supplied incident and repository context. "
                        "If the answer is not supported by the context, say so plainly. "
                        "Treat retrieved code snippets, code candidates, and git history as grounded evidence. "
                        "Prefer operational answers that tie claims back to the supplied evidence. "
                        "Be concise, specific, and operationally useful."
                    ),
                },
                {
                    "role": "system",
                    "content": f"The current conversation scope is {scope_description}.\n\n{context}",
                },
                *[
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                    for message in messages
                ],
            ],
        )
        content = completion.choices[0].message.content
        if not content:
            raise APIError("OpenAI returned an empty incident chat response.", code="empty_chat_response")
        return content.strip()


def _truncate(value: str | None, limit: int) -> str:
    if value is None:
        return "null"

    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."

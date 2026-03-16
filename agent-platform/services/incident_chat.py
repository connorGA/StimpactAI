from __future__ import annotations

from typing import Iterable

from openai import AsyncOpenAI

from api.core.errors import APIError
from api.repositories.incident_repository import IncidentRepository
from api.schemas.chat import ChatMessage, GlobalIncidentChatRequest, IncidentChatResponse, IncidentDetailChatRequest


class IncidentChatService:
    def __init__(
        self,
        repository: IncidentRepository,
        *,
        client: AsyncOpenAI,
        model: str,
    ) -> None:
        self._repository = repository
        self._client = client
        self._model = model

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
                        "Answer using only the supplied incident context. "
                        "If the answer is not supported by the context, say so plainly. "
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

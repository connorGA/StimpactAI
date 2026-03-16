from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.incident import IncidentStatus


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message content must not be blank")
        return normalized


class GlobalIncidentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    status: IncidentStatus | None = None
    incident_limit: int = Field(default=20, ge=1, le=50)


class IncidentDetailChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    event_limit: int = Field(default=50, ge=1, le=100)


class IncidentChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    referenced_incident_ids: list[str] = Field(default_factory=list)

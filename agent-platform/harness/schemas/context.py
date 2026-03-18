from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


DETAIL_TURN_LIMIT = 5


class ContextEventKind(StrEnum):
    OBSERVATION = "observation"
    ACTION = "action"
    EDIT = "edit"
    VERIFICATION = "verification"
    GIT_OPERATION = "git_operation"


class ContextEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: int = Field(ge=1)
    kind: ContextEventKind
    summary: str = Field(min_length=1, max_length=500)
    details: str | None = Field(default=None, max_length=5_000)
    file_paths: list[str] = Field(default_factory=list, max_length=25)
    tool_name: str | None = Field(default=None, max_length=128)
    tool_output: str | None = Field(default=None, max_length=2_000)
    repo_state: str | None = Field(default=None, max_length=1_000)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized


class CompressedMemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=500)


class ActiveContextWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_objective: str | None = Field(default=None, max_length=1_000)
    current_repo_state: str | None = Field(default=None, max_length=1_000)
    recent_actions: list[str] = Field(default_factory=list)
    recent_file_interactions: list[str] = Field(default_factory=list)
    recent_tool_outputs: list[str] = Field(default_factory=list)


class PromptReadyContextPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_objective: str | None = None
    current_repo_state: str | None = None
    compressed_memory: list[str] = Field(default_factory=list)
    detailed_recent_turns: list[ContextEvent] = Field(default_factory=list)
    recent_actions: list[str] = Field(default_factory=list)
    recent_file_interactions: list[str] = Field(default_factory=list)
    recent_tool_outputs: list[str] = Field(default_factory=list)
    rendered_context: str = ""

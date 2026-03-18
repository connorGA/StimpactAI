from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness.schemas.context import PromptReadyContextPacket
from harness.schemas.initializer import FeatureCatalog, FeatureSeed
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.runtime import (
    CodingAgentInputContract,
    HarnessAgentRole,
    InitializerOutputContract,
    RuntimeSessionRecord,
)
from harness.schemas.verification import FeatureVerificationState, VerificationKind


class ToolCategory(StrEnum):
    SEARCH = "search"
    VIEW = "view"
    EDIT = "edit"
    COMMAND = "command"
    BROWSER = "browser"
    GIT = "git"


class ToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=300)
    category: ToolCategory
    requires_modify_files: bool = False
    requires_verification: bool = False
    requires_git_recovery: bool = False


class ToolRegistrySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    role: HarnessAgentRole
    tools: list[ToolDescriptor] = Field(default_factory=list)


class OrchestratorSessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: HarnessAgentRole
    repository_root: str = Field(min_length=1, max_length=4096)
    objective: str | None = Field(default=None, max_length=1000)
    initializer_session_id: str | None = Field(default=None, max_length=128)
    repository_profile_override: HarnessRepositoryProfile | None = None

    @field_validator("repository_root")
    @classmethod
    def validate_repository_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repository_root must not be blank")
        return normalized


class GenerateInitializerOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    feature_seeds: list[FeatureSeed] = Field(default_factory=list)
    environment_notes: list[str] = Field(default_factory=list)
    known_constraints: list[str] = Field(default_factory=list)


class UpdateObjectiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str | None = Field(default=None, max_length=1000)


class ToolInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = Field(default=None, max_length=500)
    feature_id: str | None = Field(default=None, max_length=128)
    verification_kind: VerificationKind | None = None

    @model_validator(mode="after")
    def validate_feature_metadata(self) -> "ToolInvocationRequest":
        if self.verification_kind is not None and not self.feature_id:
            raise ValueError("feature_id is required when verification_kind is provided")
        return self


class ToolInvocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: int = Field(ge=1)
    tool_name: str = Field(min_length=1, max_length=128)
    ok: bool
    summary: str = Field(min_length=1, max_length=500)


class ToolInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    ok: bool
    turn_id: int = Field(ge=1)
    result: dict[str, Any] = Field(default_factory=dict)
    prompt_context: PromptReadyContextPacket
    feature_state: FeatureVerificationState | None = None


class HarnessSessionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: RuntimeSessionRecord
    prompt_context: PromptReadyContextPacket
    feature_catalog: FeatureCatalog | None = None
    available_tools: ToolRegistrySnapshot
    turn_count: int = Field(ge=0, default=0)
    tool_call_count: int = Field(ge=0, default=0)


class CodingHandoffResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coding_input: CodingAgentInputContract
    coding_session: HarnessSessionSnapshot
    initializer_session: HarnessSessionSnapshot

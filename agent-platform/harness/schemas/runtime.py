from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.schemas.context import PromptReadyContextPacket
from harness.schemas.initializer import FeatureCatalog, GitCheckpointStrategy, InitScriptOutput
from harness.schemas.profile import HarnessRepositoryProfile


class HarnessAgentRole(StrEnum):
    INITIALIZER = "initializer"
    CODING = "coding"


class RuntimeSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class AgentPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_scaffold_environment: bool = False
    can_modify_files: bool = False
    can_run_verification: bool = False
    can_manage_git_recovery: bool = False


class InitializerOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_root: str
    repository_profile: HarnessRepositoryProfile
    summary: str = Field(min_length=1, max_length=1_000)
    init_script: InitScriptOutput
    feature_catalog: FeatureCatalog
    checkpoint_strategy: GitCheckpointStrategy
    environment_notes: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    known_constraints: list[str] = Field(default_factory=list)
    generated_at: datetime


class CodingAgentInputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    repository_root: str
    repository_profile: HarnessRepositoryProfile
    current_objective: str | None = None
    initializer_output: InitializerOutputContract
    context_packet: PromptReadyContextPacket


class RuntimeSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    role: HarnessAgentRole
    status: RuntimeSessionStatus
    repository_root: str
    repository_profile: HarnessRepositoryProfile
    objective: str | None = Field(default=None, max_length=1_000)
    prompt_template: str = Field(min_length=1)
    permissions: AgentPermissions
    initializer_output: InitializerOutputContract | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("repository_root")
    @classmethod
    def validate_repository_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repository_root must not be blank")
        return normalized

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.schemas.verification import FeatureVerificationState, VerificationKind


class FeatureStatus(StrEnum):
    UNVERIFIED = "unverified"
    FAILING = "failing"


class FeatureSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    verification_method: str = Field(min_length=1, max_length=200)
    reproduction_command: str | None = Field(default=None, max_length=4_000)
    verification_command: str | None = Field(default=None, max_length=4_000)
    required_verification: list[VerificationKind] = Field(default_factory=list)
    browser_required: bool = True
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "feature_name",
        "description",
        "verification_method",
        "reproduction_command",
        "verification_command",
    )
    @classmethod
    def validate_seed_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class FeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    feature_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    status: FeatureStatus
    verification_method: str = Field(min_length=1, max_length=200)
    reproduction_command: str | None = Field(default=None, max_length=4_000)
    verification_command: str | None = Field(default=None, max_length=4_000)
    required_verification: list[VerificationKind] = Field(default_factory=list)
    verification_state: FeatureVerificationState
    last_verified_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "id",
        "feature_name",
        "description",
        "verification_method",
        "reproduction_command",
        "verification_command",
    )
    @classmethod
    def validate_nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class FeatureCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    repository_root: str = Field(min_length=1, max_length=4096)
    features: list[FeatureRecord] = Field(default_factory=list)


class InitScriptOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)


class GitCheckpointStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_message_prefix: str = Field(min_length=1, max_length=200)
    last_known_good_tag_prefix: str = Field(min_length=1, max_length=200)
    reset_command_summary: str = Field(min_length=1, max_length=500)
    notes: list[str] = Field(default_factory=list)

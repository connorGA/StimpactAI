from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    CODE_CHANGED = "code_changed"
    UNIT_VERIFIED = "unit_verified"
    INTEGRATION_VERIFIED = "integration_verified"
    BROWSER_VERIFIED = "browser_verified"
    FULLY_VERIFIED = "fully_verified"
    FAILED_VERIFICATION = "failed_verification"


class VerificationKind(StrEnum):
    UNIT = "unit"
    INTEGRATION = "integration"
    BROWSER = "browser"


class VerificationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: VerificationKind
    passed: bool
    summary: str = Field(min_length=1, max_length=1_000)
    attempted_at: datetime | None = None

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized


class FeatureVerificationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus = VerificationStatus.UNVERIFIED
    attempted: list[VerificationAttempt] = Field(default_factory=list)
    passed: list[VerificationKind] = Field(default_factory=list)
    remaining: list[VerificationKind] = Field(default_factory=list)
    browser_required: bool = True
    can_mark_complete: bool = False
    completion_blockers: list[str] = Field(default_factory=list)

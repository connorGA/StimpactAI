from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.auth import (
    OrganizationAccessRequestRecord,
    OrganizationAccessRequestStatus,
    OrganizationInviteRecord,
    OrganizationInviteStatus,
    OrganizationMembershipRole,
    OrganizationMembershipWithOrganizationRecord,
    OrganizationRecord,
    ProjectRecord,
    SeatPolicy,
    SubscriptionPlan,
    SubscriptionRecord,
    SubscriptionStatus,
    UserRecord,
)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class OrganizationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: OrganizationRecord) -> "OrganizationSummaryResponse":
        return cls(**record.model_dump(mode="json"))


class UserSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    full_name: str
    email_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: UserRecord) -> "UserSummaryResponse":
        payload = record.model_dump(mode="json")
        payload.pop("password_hash", None)
        return cls(**payload)


class OrganizationMembershipSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: OrganizationSummaryResponse
    role: OrganizationMembershipRole

    @classmethod
    def from_record(
        cls,
        record: OrganizationMembershipWithOrganizationRecord,
    ) -> "OrganizationMembershipSummaryResponse":
        return cls(
            organization=OrganizationSummaryResponse.from_record(record.organization),
            role=record.membership.role,
        )


class ProjectSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    slug: str
    name: str
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ProjectRecord) -> "ProjectSummaryResponse":
        return cls(**record.model_dump(mode="json"))


class SubscriptionSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    plan: SubscriptionPlan
    status: SubscriptionStatus
    included_projects: int
    additional_project_price_cents: int
    seat_policy: SeatPolicy
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: SubscriptionRecord) -> "SubscriptionSummaryResponse":
        return cls(**record.model_dump(mode="json"))


class OrganizationInviteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    email: str
    role: OrganizationMembershipRole
    status: OrganizationInviteStatus
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: OrganizationInviteRecord) -> "OrganizationInviteResponse":
        payload = record.model_dump(mode="json")
        payload.pop("token_hash", None)
        payload.pop("invited_by_user_id", None)
        return cls(**payload)


class AccessRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    email: str
    full_name: str
    status: OrganizationAccessRequestStatus
    reviewed_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: OrganizationAccessRequestRecord) -> "AccessRequestResponse":
        return cls(**record.model_dump(mode="json"))


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    user: UserSummaryResponse
    organization: OrganizationSummaryResponse
    role: OrganizationMembershipRole
    memberships: list[OrganizationMembershipSummaryResponse] = Field(default_factory=list)
    projects: list[ProjectSummaryResponse] = Field(default_factory=list)
    subscription: SubscriptionSummaryResponse | None = None


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: SubscriptionPlan
    organization_name: str = Field(min_length=2, max_length=120)
    organization_slug: str = Field(min_length=2, max_length=64)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("organization_name", "full_name", "email", "password")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        return _normalize_required_text(value, field_name=info.field_name)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="email").lower()
        if "@" not in normalized:
            raise ValueError("email must be valid")
        return normalized

    @field_validator("organization_slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="organization_slug").lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("organization slug must use lowercase letters, numbers, and dashes")
        return normalized


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="email").lower()
        if "@" not in normalized:
            raise ValueError("email must be valid")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="password")


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=64)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="name")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="slug").lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("project slug must use lowercase letters, numbers, and dashes")
        return normalized


class CreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=320)
    role: OrganizationMembershipRole = OrganizationMembershipRole.MEMBER

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="email").lower()
        if "@" not in normalized:
            raise ValueError("email must be valid")
        return normalized


class CreateInviteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite: OrganizationInviteResponse
    invite_token: str


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_token: str = Field(min_length=12, max_length=500)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("invite_token", "full_name", "password")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _normalize_required_text(value, field_name=info.field_name)


class CreateAccessRequestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_slug: str = Field(min_length=2, max_length=64)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)

    @field_validator("organization_slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="organization_slug").lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("organization slug must use lowercase letters, numbers, and dashes")
        return normalized

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="full_name")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = _normalize_required_text(value, field_name="email").lower()
        if "@" not in normalized:
            raise ValueError("email must be valid")
        return normalized


class ApproveAccessRequestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: OrganizationMembershipRole = OrganizationMembershipRole.MEMBER


class ApproveAccessRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_request: AccessRequestResponse
    invite: OrganizationInviteResponse
    invite_token: str

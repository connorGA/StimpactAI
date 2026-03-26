from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class OrganizationMembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class OrganizationInviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class OrganizationAccessRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SubscriptionPlan(StrEnum):
    BASIC = "basic"
    GROWTH = "growth"
    SCALE = "scale"


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class SeatPolicy(StrEnum):
    UNLIMITED = "unlimited"


class UserRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    full_name: str
    password_hash: str
    email_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "UserRecord":
        return cls(
            id=str(row["id"]),
            email=str(row["email"]),
            full_name=str(row["full_name"]),
            password_hash=str(row["password_hash"]),
            email_verified_at=row["email_verified_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrganizationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "OrganizationRecord":
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrganizationMembershipRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    user_id: str
    role: OrganizationMembershipRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "OrganizationMembershipRecord":
        return cls(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            user_id=str(row["user_id"]),
            role=OrganizationMembershipRole(str(row["role"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrganizationMembershipWithOrganizationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership: OrganizationMembershipRecord
    organization: OrganizationRecord

    @classmethod
    def from_db_row(cls, row: Any) -> "OrganizationMembershipWithOrganizationRecord":
        return cls(
            membership=OrganizationMembershipRecord(
                id=str(row["membership_id"]),
                organization_id=str(row["organization_id"]),
                user_id=str(row["user_id"]),
                role=OrganizationMembershipRole(str(row["role"])),
                created_at=row["membership_created_at"],
                updated_at=row["membership_updated_at"],
            ),
            organization=OrganizationRecord(
                id=str(row["organization_id"]),
                name=str(row["organization_name"]),
                slug=str(row["organization_slug"]),
                created_at=row["organization_created_at"],
                updated_at=row["organization_updated_at"],
            ),
        )


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    slug: str
    name: str
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "ProjectRecord":
        return cls(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            slug=str(row["slug"]),
            name=str(row["name"]),
            created_by_user_id=str(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SubscriptionRecord(BaseModel):
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
    def from_db_row(cls, row: Any) -> "SubscriptionRecord":
        return cls(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            plan=SubscriptionPlan(str(row["plan"])),
            status=SubscriptionStatus(str(row["status"])),
            included_projects=int(row["included_projects"]),
            additional_project_price_cents=int(row["additional_project_price_cents"]),
            seat_policy=SeatPolicy(str(row["seat_policy"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrganizationInviteRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    email: str
    role: OrganizationMembershipRole
    token_hash: str
    invited_by_user_id: str | None = None
    status: OrganizationInviteStatus
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> "OrganizationInviteRecord":
        return cls(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            email=str(row["email"]),
            role=OrganizationMembershipRole(str(row["role"])),
            token_hash=str(row["token_hash"]),
            invited_by_user_id=str(row["invited_by_user_id"]) if row["invited_by_user_id"] is not None else None,
            status=OrganizationInviteStatus(str(row["status"])),
            expires_at=row["expires_at"],
            accepted_at=row["accepted_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrganizationAccessRequestRecord(BaseModel):
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
    def from_db_row(cls, row: Any) -> "OrganizationAccessRequestRecord":
        return cls(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            email=str(row["email"]),
            full_name=str(row["full_name"]),
            status=OrganizationAccessRequestStatus(str(row["status"])),
            reviewed_by_user_id=str(row["reviewed_by_user_id"]) if row["reviewed_by_user_id"] is not None else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

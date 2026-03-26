from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg

from api.core.errors import PersistenceError
from models.auth import (
    OrganizationAccessRequestRecord,
    OrganizationAccessRequestStatus,
    OrganizationInviteRecord,
    OrganizationInviteStatus,
    OrganizationMembershipRecord,
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

INSERT_USER_SQL = """
INSERT INTO users (
    id, email, full_name, password_hash, email_verified_at
) VALUES (
    $1, $2, $3, $4, $5
)
RETURNING *;
"""

GET_USER_BY_EMAIL_SQL = """
SELECT *
FROM users
WHERE email = $1
LIMIT 1;
"""

GET_USER_SQL = """
SELECT *
FROM users
WHERE id = $1
LIMIT 1;
"""

INSERT_ORGANIZATION_SQL = """
INSERT INTO organizations (
    id, name, slug
) VALUES (
    $1, $2, $3
)
RETURNING *;
"""

GET_ORGANIZATION_SQL = """
SELECT *
FROM organizations
WHERE id = $1
LIMIT 1;
"""

GET_ORGANIZATION_BY_SLUG_SQL = """
SELECT *
FROM organizations
WHERE slug = $1
LIMIT 1;
"""

INSERT_MEMBERSHIP_SQL = """
INSERT INTO organization_memberships (
    id, organization_id, user_id, role
) VALUES (
    $1, $2, $3, $4
)
ON CONFLICT (organization_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    updated_at = NOW()
RETURNING *;
"""

GET_MEMBERSHIP_SQL = """
SELECT *
FROM organization_memberships
WHERE organization_id = $1
  AND user_id = $2
LIMIT 1;
"""

LIST_USER_MEMBERSHIPS_SQL = """
SELECT
    organization_memberships.id AS membership_id,
    organization_memberships.organization_id,
    organization_memberships.user_id,
    organization_memberships.role,
    organization_memberships.created_at AS membership_created_at,
    organization_memberships.updated_at AS membership_updated_at,
    organizations.name AS organization_name,
    organizations.slug AS organization_slug,
    organizations.created_at AS organization_created_at,
    organizations.updated_at AS organization_updated_at
FROM organization_memberships
JOIN organizations ON organizations.id = organization_memberships.organization_id
WHERE organization_memberships.user_id = $1
ORDER BY organizations.created_at ASC;
"""

INSERT_SUBSCRIPTION_SQL = """
INSERT INTO subscriptions (
    id, organization_id, plan, status, included_projects, additional_project_price_cents, seat_policy
) VALUES (
    $1, $2, $3, $4, $5, $6, $7
)
ON CONFLICT (organization_id) DO UPDATE
SET plan = EXCLUDED.plan,
    status = EXCLUDED.status,
    included_projects = EXCLUDED.included_projects,
    additional_project_price_cents = EXCLUDED.additional_project_price_cents,
    seat_policy = EXCLUDED.seat_policy,
    updated_at = NOW()
RETURNING *;
"""

GET_SUBSCRIPTION_BY_ORG_SQL = """
SELECT *
FROM subscriptions
WHERE organization_id = $1
LIMIT 1;
"""

INSERT_PROJECT_SQL = """
INSERT INTO projects (
    id, organization_id, slug, name, created_by_user_id
) VALUES (
    $1, $2, $3, $4, $5
)
RETURNING *;
"""

LIST_ORGANIZATION_PROJECTS_SQL = """
SELECT *
FROM projects
WHERE organization_id = $1
ORDER BY created_at ASC;
"""

GET_PROJECT_SQL = """
SELECT *
FROM projects
WHERE id = $1
LIMIT 1;
"""

GET_PROJECT_FOR_USER_SQL = """
SELECT projects.*
FROM projects
JOIN organization_memberships
  ON organization_memberships.organization_id = projects.organization_id
WHERE projects.id = $1
  AND organization_memberships.user_id = $2
LIMIT 1;
"""

INSERT_INVITE_SQL = """
INSERT INTO organization_invites (
    id, organization_id, email, role, token_hash, invited_by_user_id, status, expires_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
RETURNING *;
"""

LIST_ORGANIZATION_INVITES_SQL = """
SELECT *
FROM organization_invites
WHERE organization_id = $1
ORDER BY created_at DESC;
"""

GET_INVITE_BY_TOKEN_HASH_SQL = """
SELECT *
FROM organization_invites
WHERE token_hash = $1
LIMIT 1;
"""

MARK_INVITE_ACCEPTED_SQL = """
UPDATE organization_invites
SET status = $2,
    accepted_at = NOW(),
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""

INSERT_ACCESS_REQUEST_SQL = """
INSERT INTO organization_access_requests (
    id, organization_id, email, full_name, status
) VALUES (
    $1, $2, $3, $4, $5
)
RETURNING *;
"""

LIST_ACCESS_REQUESTS_SQL = """
SELECT *
FROM organization_access_requests
WHERE organization_id = $1
ORDER BY created_at DESC;
"""

MARK_ACCESS_REQUEST_APPROVED_SQL = """
UPDATE organization_access_requests
SET status = $2,
    reviewed_by_user_id = $3,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
"""


class IdentityRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self._pool = pool

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        row = await self._fetchrow(GET_USER_BY_EMAIL_SQL, email.lower(), allow_missing=True)
        if row is None:
            return None
        return UserRecord.from_db_row(row)

    async def get_user(self, user_id: str) -> UserRecord | None:
        row = await self._fetchrow(GET_USER_SQL, user_id, allow_missing=True)
        if row is None:
            return None
        return UserRecord.from_db_row(row)

    async def get_organization(self, organization_id: str) -> OrganizationRecord | None:
        row = await self._fetchrow(GET_ORGANIZATION_SQL, organization_id, allow_missing=True)
        if row is None:
            return None
        return OrganizationRecord.from_db_row(row)

    async def get_organization_by_slug(self, slug: str) -> OrganizationRecord | None:
        row = await self._fetchrow(GET_ORGANIZATION_BY_SLUG_SQL, slug, allow_missing=True)
        if row is None:
            return None
        return OrganizationRecord.from_db_row(row)

    async def get_membership(self, organization_id: str, user_id: str) -> OrganizationMembershipRecord | None:
        row = await self._fetchrow(GET_MEMBERSHIP_SQL, organization_id, user_id, allow_missing=True)
        if row is None:
            return None
        return OrganizationMembershipRecord.from_db_row(row)

    async def list_user_memberships(
        self,
        user_id: str,
    ) -> list[OrganizationMembershipWithOrganizationRecord]:
        rows = await self._fetch(LIST_USER_MEMBERSHIPS_SQL, user_id)
        return [OrganizationMembershipWithOrganizationRecord.from_db_row(row) for row in rows]

    async def get_subscription_by_organization(self, organization_id: str) -> SubscriptionRecord | None:
        row = await self._fetchrow(GET_SUBSCRIPTION_BY_ORG_SQL, organization_id, allow_missing=True)
        if row is None:
            return None
        return SubscriptionRecord.from_db_row(row)

    async def list_projects_for_organization(self, organization_id: str) -> list[ProjectRecord]:
        rows = await self._fetch(LIST_ORGANIZATION_PROJECTS_SQL, organization_id)
        return [ProjectRecord.from_db_row(row) for row in rows]

    async def get_project(self, project_id: str) -> ProjectRecord | None:
        row = await self._fetchrow(GET_PROJECT_SQL, project_id, allow_missing=True)
        if row is None:
            return None
        return ProjectRecord.from_db_row(row)

    async def get_project_for_user(self, project_id: str, user_id: str) -> ProjectRecord | None:
        row = await self._fetchrow(GET_PROJECT_FOR_USER_SQL, project_id, user_id, allow_missing=True)
        if row is None:
            return None
        return ProjectRecord.from_db_row(row)

    async def list_organization_invites(self, organization_id: str) -> list[OrganizationInviteRecord]:
        rows = await self._fetch(LIST_ORGANIZATION_INVITES_SQL, organization_id)
        return [OrganizationInviteRecord.from_db_row(row) for row in rows]

    async def get_invite_by_token_hash(self, token_hash: str) -> OrganizationInviteRecord | None:
        row = await self._fetchrow(GET_INVITE_BY_TOKEN_HASH_SQL, token_hash, allow_missing=True)
        if row is None:
            return None
        return OrganizationInviteRecord.from_db_row(row)

    async def list_access_requests(self, organization_id: str) -> list[OrganizationAccessRequestRecord]:
        rows = await self._fetch(LIST_ACCESS_REQUESTS_SQL, organization_id)
        return [OrganizationAccessRequestRecord.from_db_row(row) for row in rows]

    async def signup_organization_owner(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        organization_name: str,
        organization_slug: str,
        plan: SubscriptionPlan,
        included_projects: int,
        additional_project_price_cents: int,
    ) -> tuple[UserRecord, OrganizationRecord, OrganizationMembershipRecord, SubscriptionRecord]:
        normalized_email = email.lower()
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for identity operations.")

        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    user_row = await connection.fetchrow(
                        INSERT_USER_SQL,
                        str(uuid4()),
                        normalized_email,
                        full_name,
                        password_hash,
                        datetime.now(UTC),
                    )
                    organization_row = await connection.fetchrow(
                        INSERT_ORGANIZATION_SQL,
                        str(uuid4()),
                        organization_name,
                        organization_slug,
                    )
                    membership_row = await connection.fetchrow(
                        INSERT_MEMBERSHIP_SQL,
                        str(uuid4()),
                        str(organization_row["id"]),
                        str(user_row["id"]),
                        OrganizationMembershipRole.OWNER.value,
                    )
                    subscription_row = await connection.fetchrow(
                        INSERT_SUBSCRIPTION_SQL,
                        str(uuid4()),
                        str(organization_row["id"]),
                        plan.value,
                        SubscriptionStatus.ACTIVE.value,
                        included_projects,
                        additional_project_price_cents,
                        SeatPolicy.UNLIMITED.value,
                    )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to create the initial organization workspace.") from exc

        return (
            UserRecord.from_db_row(user_row),
            OrganizationRecord.from_db_row(organization_row),
            OrganizationMembershipRecord.from_db_row(membership_row),
            SubscriptionRecord.from_db_row(subscription_row),
        )

    async def create_project(
        self,
        *,
        organization_id: str,
        project_id: str,
        slug: str,
        name: str,
        created_by_user_id: str,
    ) -> ProjectRecord:
        row = await self._fetchrow(
            INSERT_PROJECT_SQL,
            project_id,
            organization_id,
            slug,
            name,
            created_by_user_id,
        )
        return ProjectRecord.from_db_row(row)

    async def create_invite(
        self,
        *,
        organization_id: str,
        email: str,
        role: OrganizationMembershipRole,
        token_hash: str,
        invited_by_user_id: str,
        ttl_days: int = 7,
    ) -> OrganizationInviteRecord:
        row = await self._fetchrow(
            INSERT_INVITE_SQL,
            str(uuid4()),
            organization_id,
            email.lower(),
            role.value,
            token_hash,
            invited_by_user_id,
            OrganizationInviteStatus.PENDING.value,
            datetime.now(UTC) + timedelta(days=ttl_days),
        )
        return OrganizationInviteRecord.from_db_row(row)

    async def accept_invite_with_user(
        self,
        *,
        invite: OrganizationInviteRecord,
        full_name: str,
        password_hash: str,
    ) -> tuple[UserRecord, OrganizationMembershipRecord, OrganizationInviteRecord]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for identity operations.")

        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    user_row = await connection.fetchrow(GET_USER_BY_EMAIL_SQL, invite.email)
                    if user_row is None:
                        user_row = await connection.fetchrow(
                            INSERT_USER_SQL,
                            str(uuid4()),
                            invite.email.lower(),
                            full_name,
                            password_hash,
                            datetime.now(UTC),
                        )
                    membership_row = await connection.fetchrow(
                        INSERT_MEMBERSHIP_SQL,
                        str(uuid4()),
                        invite.organization_id,
                        str(user_row["id"]),
                        invite.role.value,
                    )
                    invite_row = await connection.fetchrow(
                        MARK_INVITE_ACCEPTED_SQL,
                        invite.id,
                        OrganizationInviteStatus.ACCEPTED.value,
                    )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to accept the workspace invite.") from exc

        return (
            UserRecord.from_db_row(user_row),
            OrganizationMembershipRecord.from_db_row(membership_row),
            OrganizationInviteRecord.from_db_row(invite_row),
        )

    async def create_access_request(
        self,
        *,
        organization_id: str,
        email: str,
        full_name: str,
    ) -> OrganizationAccessRequestRecord:
        row = await self._fetchrow(
            INSERT_ACCESS_REQUEST_SQL,
            str(uuid4()),
            organization_id,
            email.lower(),
            full_name,
            OrganizationAccessRequestStatus.PENDING.value,
        )
        return OrganizationAccessRequestRecord.from_db_row(row)

    async def approve_access_request(
        self,
        *,
        access_request_id: str,
        reviewed_by_user_id: str,
        role: OrganizationMembershipRole,
        token_hash: str,
    ) -> tuple[OrganizationAccessRequestRecord, OrganizationInviteRecord]:
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for identity operations.")

        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    request_row = await connection.fetchrow(
                        MARK_ACCESS_REQUEST_APPROVED_SQL,
                        access_request_id,
                        OrganizationAccessRequestStatus.APPROVED.value,
                        reviewed_by_user_id,
                    )
                    if request_row is None:
                        raise PersistenceError("Access request was not found.")
                    invite_row = await connection.fetchrow(
                        INSERT_INVITE_SQL,
                        str(uuid4()),
                        str(request_row["organization_id"]),
                        str(request_row["email"]).lower(),
                        role.value,
                        token_hash,
                        reviewed_by_user_id,
                        OrganizationInviteStatus.PENDING.value,
                        datetime.now(UTC) + timedelta(days=7),
                    )
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to approve the access request.") from exc

        return (
            OrganizationAccessRequestRecord.from_db_row(request_row),
            OrganizationInviteRecord.from_db_row(invite_row),
        )

    async def _fetchrow(
        self,
        query: str,
        *params: object,
        allow_missing: bool = False,
    ):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for identity operations.")
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an identity query.") from exc
        if row is None and not allow_missing:
            raise PersistenceError("Identity query returned no row.")
        return row

    async def _fetch(self, query: str, *params: object):
        if self._pool is None:
            raise PersistenceError("Postgres is not configured for identity operations.")
        try:
            async with self._pool.acquire() as connection:
                return await connection.fetch(query, *params)
        except asyncpg.PostgresError as exc:
            raise PersistenceError("Failed to execute an identity query.") from exc

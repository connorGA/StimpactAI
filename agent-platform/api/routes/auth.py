from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from api.core.errors import APIError
from api.core.security import (
    build_session_token,
    get_current_user_context,
    get_identity_repository,
    hash_password,
    hash_token_value,
    verify_password,
)
from api.repositories.identity_repository import IdentityRepository
from api.schemas.auth import (
    AcceptInviteRequest,
    AccessRequestResponse,
    ApproveAccessRequestRequest,
    ApproveAccessRequestResponse,
    AuthSessionResponse,
    CreateAccessRequestRequest,
    CreateInviteRequest,
    CreateInviteResponse,
    CreateProjectRequest,
    LoginRequest,
    OrganizationInviteResponse,
    OrganizationMembershipSummaryResponse,
    OrganizationSummaryResponse,
    ProjectSummaryResponse,
    SignupRequest,
    SubscriptionSummaryResponse,
    UserSummaryResponse,
)
from models.auth import (
    OrganizationInviteStatus,
    OrganizationMembershipRole,
    SubscriptionPlan,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _plan_entitlements(plan: SubscriptionPlan) -> tuple[int, int]:
    if plan is SubscriptionPlan.SCALE:
        return 3, 3000
    return 1, 0


async def _build_session_response(
    *,
    repository: IdentityRepository,
    user_id: str,
    organization_id: str,
) -> AuthSessionResponse:
    user = await repository.get_user(user_id)
    organization = await repository.get_organization(organization_id)
    membership = await repository.get_membership(organization_id, user_id)
    subscription = await repository.get_subscription_by_organization(organization_id)
    memberships = await repository.list_user_memberships(user_id)
    projects = await repository.list_projects_for_organization(organization_id)

    if user is None or organization is None or membership is None:
        raise APIError(
            "The authenticated account could not be resolved.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="account_not_found",
        )

    token = build_session_token(
        user_id=user.id,
        organization_id=organization.id,
        role=membership.role,
    )
    return AuthSessionResponse(
        access_token=token,
        user=UserSummaryResponse.from_record(user),
        organization=OrganizationSummaryResponse.from_record(organization),
        role=membership.role,
        memberships=[OrganizationMembershipSummaryResponse.from_record(item) for item in memberships],
        projects=[ProjectSummaryResponse.from_record(item) for item in projects],
        subscription=SubscriptionSummaryResponse.from_record(subscription) if subscription else None,
    )


@router.post("/signup", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AuthSessionResponse:
    existing_user = await repository.get_user_by_email(payload.email)
    if existing_user is not None:
        raise APIError(
            "An account with that email already exists.",
            status_code=status.HTTP_409_CONFLICT,
            code="email_in_use",
        )
    existing_org = await repository.get_organization_by_slug(payload.organization_slug)
    if existing_org is not None:
        raise APIError(
            "That workspace slug is already in use.",
            status_code=status.HTTP_409_CONFLICT,
            code="organization_slug_in_use",
        )

    included_projects, additional_project_price_cents = _plan_entitlements(payload.plan)
    user, organization, _membership, _subscription = await repository.signup_organization_owner(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        organization_name=payload.organization_name,
        organization_slug=payload.organization_slug,
        plan=payload.plan,
        included_projects=included_projects,
        additional_project_price_cents=additional_project_price_cents,
    )
    return await _build_session_response(
        repository=repository,
        user_id=user.id,
        organization_id=organization.id,
    )


@router.post("/login", response_model=AuthSessionResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AuthSessionResponse:
    user = await repository.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise APIError(
            "Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
        )
    memberships = await repository.list_user_memberships(user.id)
    if not memberships:
        raise APIError(
            "This account is not assigned to a workspace yet.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="membership_required",
        )
    return await _build_session_response(
        repository=repository,
        user_id=user.id,
        organization_id=memberships[0].organization.id,
    )


@router.get("/me", response_model=AuthSessionResponse, status_code=status.HTTP_200_OK)
async def current_session(
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AuthSessionResponse:
    return await _build_session_response(
        repository=repository,
        user_id=context.user_id,
        organization_id=context.organization_id,
    )


@router.post("/accept-invite", response_model=AuthSessionResponse, status_code=status.HTTP_200_OK)
async def accept_invite(
    payload: AcceptInviteRequest,
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AuthSessionResponse:
    invite = await repository.get_invite_by_token_hash(hash_token_value(payload.invite_token))
    if invite is None:
        raise APIError(
            "That invite token is invalid.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="invite_not_found",
        )
    if invite.status is not OrganizationInviteStatus.PENDING:
        raise APIError(
            "That invite is no longer pending.",
            status_code=status.HTTP_409_CONFLICT,
            code="invite_not_pending",
        )
    if invite.expires_at <= datetime.now(UTC):
        raise APIError(
            "That invite has expired.",
            status_code=status.HTTP_410_GONE,
            code="invite_expired",
        )
    existing_user = await repository.get_user_by_email(invite.email)
    if existing_user is not None and not verify_password(payload.password, existing_user.password_hash):
        raise APIError(
            "That email already belongs to an account. Use the existing password to accept the invite.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
        )
    user, membership, _updated_invite = await repository.accept_invite_with_user(
        invite=invite,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    return await _build_session_response(
        repository=repository,
        user_id=user.id,
        organization_id=membership.organization_id,
    )


@router.post("/access-requests", response_model=AccessRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_access_request(
    payload: CreateAccessRequestRequest,
    repository: IdentityRepository = Depends(get_identity_repository),
) -> AccessRequestResponse:
    organization = await repository.get_organization_by_slug(payload.organization_slug)
    if organization is None:
        raise APIError(
            "That workspace was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="organization_not_found",
        )
    record = await repository.create_access_request(
        organization_id=organization.id,
        email=payload.email,
        full_name=payload.full_name,
    )
    return AccessRequestResponse.from_record(record)


@router.post("/projects", response_model=ProjectSummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> ProjectSummaryResponse:
    membership = await repository.get_membership(context.organization_id, context.user_id)
    if membership is None:
        raise APIError(
            "The current user does not have workspace access.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    if membership.role not in {OrganizationMembershipRole.OWNER, OrganizationMembershipRole.ADMIN}:
        raise APIError(
            "Only workspace owners and admins can create projects.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="project_create_forbidden",
        )
    organization = await repository.get_organization(context.organization_id)
    if organization is None:
        raise APIError(
            "The current workspace could not be resolved.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="organization_not_found",
        )
    project_id = f"{organization.slug}-{payload.slug}"
    record = await repository.create_project(
        organization_id=context.organization_id,
        project_id=project_id,
        slug=payload.slug,
        name=payload.name,
        created_by_user_id=context.user_id,
    )
    return ProjectSummaryResponse.from_record(record)


@router.get("/organizations/{organization_id}/invites", response_model=list[OrganizationInviteResponse])
async def list_invites(
    organization_id: str,
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> list[OrganizationInviteResponse]:
    if organization_id != context.organization_id:
        raise APIError(
            "The requested workspace is not active for this session.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    return [
        OrganizationInviteResponse.from_record(record)
        for record in await repository.list_organization_invites(organization_id)
    ]


@router.post("/organizations/{organization_id}/invites", response_model=CreateInviteResponse)
async def create_invite(
    organization_id: str,
    payload: CreateInviteRequest,
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> CreateInviteResponse:
    membership = await repository.get_membership(context.organization_id, context.user_id)
    if organization_id != context.organization_id or membership is None:
        raise APIError(
            "The requested workspace is not active for this session.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    if membership.role not in {OrganizationMembershipRole.OWNER, OrganizationMembershipRole.ADMIN}:
        raise APIError(
            "Only workspace owners and admins can invite teammates.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="invite_forbidden",
        )
    plaintext_token = secrets.token_urlsafe(24)
    invite = await repository.create_invite(
        organization_id=organization_id,
        email=payload.email,
        role=payload.role,
        token_hash=hash_token_value(plaintext_token),
        invited_by_user_id=context.user_id,
    )
    return CreateInviteResponse(
        invite=OrganizationInviteResponse.from_record(invite),
        invite_token=plaintext_token,
    )


@router.get("/organizations/{organization_id}/access-requests", response_model=list[AccessRequestResponse])
async def list_access_requests(
    organization_id: str,
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> list[AccessRequestResponse]:
    membership = await repository.get_membership(context.organization_id, context.user_id)
    if organization_id != context.organization_id or membership is None:
        raise APIError(
            "The requested workspace is not active for this session.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    if membership.role not in {OrganizationMembershipRole.OWNER, OrganizationMembershipRole.ADMIN}:
        raise APIError(
            "Only workspace owners and admins can review access requests.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="access_request_forbidden",
        )
    return [
        AccessRequestResponse.from_record(record)
        for record in await repository.list_access_requests(organization_id)
    ]


@router.post(
    "/organizations/{organization_id}/access-requests/{access_request_id}/approve",
    response_model=ApproveAccessRequestResponse,
)
async def approve_access_request(
    organization_id: str,
    access_request_id: str,
    payload: ApproveAccessRequestRequest,
    context=Depends(get_current_user_context),
    repository: IdentityRepository = Depends(get_identity_repository),
) -> ApproveAccessRequestResponse:
    membership = await repository.get_membership(context.organization_id, context.user_id)
    if organization_id != context.organization_id or membership is None:
        raise APIError(
            "The requested workspace is not active for this session.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="organization_access_denied",
        )
    if membership.role not in {OrganizationMembershipRole.OWNER, OrganizationMembershipRole.ADMIN}:
        raise APIError(
            "Only workspace owners and admins can approve access requests.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="access_request_forbidden",
        )
    plaintext_token = secrets.token_urlsafe(24)
    access_request, invite = await repository.approve_access_request(
        access_request_id=access_request_id,
        reviewed_by_user_id=context.user_id,
        role=payload.role,
        token_hash=hash_token_value(plaintext_token),
    )
    if access_request.organization_id != organization_id:
        raise APIError(
            "The access request was not found for this workspace.",
            status_code=status.HTTP_404_NOT_FOUND,
            code="access_request_not_found",
        )
    return ApproveAccessRequestResponse(
        access_request=AccessRequestResponse.from_record(access_request),
        invite=OrganizationInviteResponse.from_record(invite),
        invite_token=plaintext_token,
    )

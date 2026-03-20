from __future__ import annotations

from api.schemas.autonomous import AutonomousRunCreateRequest
from harness.schemas.autonomous import (
    AutonomousApprovalStatus,
    AutonomousExecutionMode,
    AutonomousPolicyDecision,
)
from models.control_plane import RepoProfileRecord
from models.incident import IncidentRecord, IncidentSeverity


class AutonomousPolicyService:
    def evaluate(
        self,
        *,
        incident: IncidentRecord,
        repo_profile: RepoProfileRecord | None,
        request: AutonomousRunCreateRequest,
        browser_verification_supported: bool = False,
    ) -> tuple[AutonomousPolicyDecision, AutonomousApprovalStatus]:
        allow_writeback = bool(request.allow_writeback)
        require_browser_verification = browser_verification_supported and incident.severity in {
            IncidentSeverity.HIGH,
            IncidentSeverity.CRITICAL,
        }
        requires_human_approval = bool(request.require_human_approval)
        reasons: list[str] = []

        if request.execution_mode is AutonomousExecutionMode.REPAIR_AND_PROPOSE and not allow_writeback:
            allow_writeback = True
            reasons.append("Repair-and-propose mode enables write-back eligibility.")

        if request.execution_mode is AutonomousExecutionMode.INVESTIGATE_ONLY:
            reasons.append("Investigate-only mode disables write-back.")
            allow_writeback = False

        if incident.severity is IncidentSeverity.CRITICAL:
            requires_human_approval = True
            reasons.append("Critical incidents require human approval before promotion.")

        if repo_profile is None:
            reasons.append("No active repo profile is configured; sandbox-backed verification is unavailable.")

        decision = AutonomousPolicyDecision(
            auto_run_allowed=repo_profile is not None,
            requires_human_approval=requires_human_approval,
            allow_writeback=allow_writeback,
            allowed_execution_backends=[
                request.requested_backend or "kubernetes",
                "local",
            ],
            allowed_tool_categories=(
                ["search", "view", "command", "browser"]
                if request.execution_mode is AutonomousExecutionMode.INVESTIGATE_ONLY
                else ["search", "view", "edit", "command", "browser", "git"]
            ),
            require_browser_verification=require_browser_verification,
            max_repair_attempts=2,
            max_retry_budget=2,
            reasons=reasons,
        )
        approval_status = (
            AutonomousApprovalStatus.PENDING
            if decision.requires_human_approval
            else AutonomousApprovalStatus.NOT_REQUIRED
        )
        return decision, approval_status

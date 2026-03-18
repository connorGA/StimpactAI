from __future__ import annotations

from datetime import UTC, datetime

from harness.schemas.verification import (
    FeatureVerificationState,
    VerificationAttempt,
    VerificationKind,
    VerificationStatus,
)


class VerificationRulesEngine:
    def build_initial_state(
        self,
        *,
        required_verification: list[VerificationKind] | None = None,
        browser_required: bool = True,
    ) -> FeatureVerificationState:
        required = self._normalize_required(required_verification, browser_required)
        blockers = self._build_blockers(
            required=required,
            passed=[],
            status=VerificationStatus.UNVERIFIED,
        )
        return FeatureVerificationState(
            status=VerificationStatus.UNVERIFIED,
            attempted=[],
            passed=[],
            remaining=required,
            browser_required=browser_required,
            can_mark_complete=False,
            completion_blockers=blockers,
        )

    def mark_code_changed(self, state: FeatureVerificationState) -> FeatureVerificationState:
        required = self._required_from_state(state)
        blockers = self._build_blockers(
            required=required,
            passed=[],
            status=VerificationStatus.CODE_CHANGED,
        )
        return state.model_copy(
            update={
                "status": VerificationStatus.CODE_CHANGED,
                "passed": [],
                "remaining": required,
                "can_mark_complete": False,
                "completion_blockers": blockers,
            }
        )

    def record_attempt(
        self,
        *,
        state: FeatureVerificationState,
        kind: VerificationKind,
        passed: bool,
        summary: str,
        attempted_at: datetime | None = None,
    ) -> FeatureVerificationState:
        attempts = list(state.attempted)
        attempts.append(
            VerificationAttempt(
                kind=kind,
                passed=passed,
                summary=summary,
                attempted_at=attempted_at or datetime.now(UTC),
            )
        )

        required = self._required_from_state(state)
        passed_kinds = list(state.passed)
        if passed and kind not in passed_kinds:
            passed_kinds.append(kind)
        remaining = [item for item in required if item not in passed_kinds]
        status = self._derive_status(required=required, passed=passed_kinds, failed_attempt=not passed, browser_required=state.browser_required)
        blockers = self._build_blockers(required=required, passed=passed_kinds, status=status)

        return state.model_copy(
            update={
                "status": status,
                "attempted": attempts,
                "passed": passed_kinds,
                "remaining": remaining,
                "can_mark_complete": status is VerificationStatus.FULLY_VERIFIED,
                "completion_blockers": blockers,
            }
        )

    def can_mark_complete(self, state: FeatureVerificationState) -> bool:
        return state.status is VerificationStatus.FULLY_VERIFIED and not state.remaining

    def completion_message(self, state: FeatureVerificationState) -> str:
        if self.can_mark_complete(state):
            return "Feature is fully verified and can be marked complete."
        if state.status is VerificationStatus.FAILED_VERIFICATION:
            return "Verification failed; the feature cannot be marked complete until required checks pass."
        if state.status is VerificationStatus.CODE_CHANGED:
            return "Code changed, but verification has not yet reached the required level."
        if state.completion_blockers:
            return state.completion_blockers[0]
        return "Verification is still required before completion."

    def _normalize_required(
        self,
        required_verification: list[VerificationKind] | None,
        browser_required: bool,
    ) -> list[VerificationKind]:
        normalized: list[VerificationKind] = []
        for kind in required_verification or [VerificationKind.UNIT, VerificationKind.INTEGRATION]:
            if kind not in normalized:
                normalized.append(kind)
        if browser_required and VerificationKind.BROWSER not in normalized:
            normalized.append(VerificationKind.BROWSER)
        return normalized

    def _required_from_state(self, state: FeatureVerificationState) -> list[VerificationKind]:
        ordered = list(state.passed)
        for kind in state.remaining:
            if kind not in ordered:
                ordered.append(kind)
        if state.browser_required and VerificationKind.BROWSER not in ordered:
            ordered.append(VerificationKind.BROWSER)
        return ordered

    def _derive_status(
        self,
        *,
        required: list[VerificationKind],
        passed: list[VerificationKind],
        failed_attempt: bool,
        browser_required: bool,
    ) -> VerificationStatus:
        if failed_attempt:
            return VerificationStatus.FAILED_VERIFICATION
        if all(kind in passed for kind in required):
            return VerificationStatus.FULLY_VERIFIED
        if VerificationKind.BROWSER in passed and (not browser_required or VerificationKind.BROWSER in required):
            return VerificationStatus.BROWSER_VERIFIED
        if VerificationKind.INTEGRATION in passed:
            return VerificationStatus.INTEGRATION_VERIFIED
        if VerificationKind.UNIT in passed:
            return VerificationStatus.UNIT_VERIFIED
        return VerificationStatus.CODE_CHANGED

    def _build_blockers(
        self,
        *,
        required: list[VerificationKind],
        passed: list[VerificationKind],
        status: VerificationStatus,
    ) -> list[str]:
        if status is VerificationStatus.FULLY_VERIFIED:
            return []
        if status is VerificationStatus.FAILED_VERIFICATION:
            return ["At least one verification attempt failed; rerun the required checks before marking complete."]

        remaining = [kind for kind in required if kind not in passed]
        if VerificationKind.BROWSER in remaining and passed:
            return ["Code compiles or lower-level checks passed, but browser verification still required."]
        if remaining:
            labels = ", ".join(kind.value for kind in remaining)
            return [f"Verification still required: {labels}."]
        if status is VerificationStatus.CODE_CHANGED:
            return ["Code changed, but no verification has been attempted yet."]
        return ["Verification is incomplete."]

from __future__ import annotations

from harness.runtime.verification import VerificationRulesEngine
from harness.schemas.verification import VerificationKind, VerificationStatus


def test_verification_rules_engine_blocks_completion_until_browser_check_passes() -> None:
    engine = VerificationRulesEngine()
    state = engine.build_initial_state(
        required_verification=[VerificationKind.UNIT, VerificationKind.INTEGRATION],
        browser_required=True,
    )

    state = engine.mark_code_changed(state)
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.UNIT,
        passed=True,
        summary="Targeted unit tests passed.",
    )
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.INTEGRATION,
        passed=True,
        summary="API-level integration checks passed.",
    )

    assert state.status is VerificationStatus.INTEGRATION_VERIFIED
    assert state.can_mark_complete is False
    assert VerificationKind.BROWSER in state.remaining
    assert engine.completion_message(state) == "Code compiles or lower-level checks passed, but browser verification still required."


def test_verification_rules_engine_allows_completion_after_required_checks_pass() -> None:
    engine = VerificationRulesEngine()
    state = engine.build_initial_state(
        required_verification=[VerificationKind.UNIT, VerificationKind.BROWSER],
        browser_required=True,
    )

    state = engine.mark_code_changed(state)
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.UNIT,
        passed=True,
        summary="Unit suite passed.",
    )
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.BROWSER,
        passed=True,
        summary="Browser workflow passed.",
    )

    assert state.status is VerificationStatus.FULLY_VERIFIED
    assert state.remaining == []
    assert engine.can_mark_complete(state) is True


def test_verification_rules_engine_marks_failed_verification_and_preserves_blockers() -> None:
    engine = VerificationRulesEngine()
    state = engine.build_initial_state(
        required_verification=[VerificationKind.UNIT],
        browser_required=False,
    )

    state = engine.mark_code_changed(state)
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.UNIT,
        passed=False,
        summary="Unit tests failed with assertion error.",
    )

    assert state.status is VerificationStatus.FAILED_VERIFICATION
    assert state.can_mark_complete is False
    assert engine.completion_message(state).startswith("Verification failed")


def test_verification_rules_engine_resets_passed_checks_after_new_code_change() -> None:
    engine = VerificationRulesEngine()
    state = engine.build_initial_state(
        required_verification=[VerificationKind.UNIT],
        browser_required=False,
    )
    state = engine.mark_code_changed(state)
    state = engine.record_attempt(
        state=state,
        kind=VerificationKind.UNIT,
        passed=True,
        summary="Unit tests passed.",
    )

    state = engine.mark_code_changed(state)

    assert state.status is VerificationStatus.CODE_CHANGED
    assert state.passed == []
    assert state.remaining == [VerificationKind.UNIT]
    assert state.can_mark_complete is False

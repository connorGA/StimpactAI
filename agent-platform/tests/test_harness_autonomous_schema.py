from __future__ import annotations

from harness.schemas.autonomous import AutonomousDecision, AutonomousDecisionAction


def test_autonomous_decision_accepts_null_arguments_for_complete_action() -> None:
    decision = AutonomousDecision.model_validate(
        {
            "summary": "Verification succeeded.",
            "rationale": "The task is done.",
            "action": AutonomousDecisionAction.COMPLETE,
            "arguments": None,
        }
    )

    assert decision.arguments == {}

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from harness.autonomous.decision_engine import OpenAIAutonomousDecisionEngine
from harness.schemas.autonomous import AutonomousDecisionAction


class _Dumpable:
    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        return {"mode": mode}


def _completion_with_content(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


@pytest.mark.asyncio
async def test_openai_autonomous_decision_engine_retries_then_succeeds(monkeypatch) -> None:
    engine = OpenAIAutonomousDecisionEngine(client=object(), model="test-model")
    attempts = 0

    async def fake_request(prompt_payload: dict[str, object]):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.TimeoutError()
        return _completion_with_content(
            json.dumps(
                {
                    "summary": "Run verification",
                    "rationale": "Retry succeeded.",
                    "action": "invoke_tool",
                    "selected_tool": "run_command",
                    "arguments": {"command": "pytest -q"},
                    "arguments_summary": "Run pytest",
                    "feature_id": "feature-1",
                    "verification_kind": "integration",
                }
            )
        )

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(engine, "_request_completion", fake_request)
    monkeypatch.setattr("harness.autonomous.decision_engine.asyncio.sleep", fake_sleep)

    decision = await engine.decide(
        run=_Dumpable(),
        coding_session=_Dumpable(),
        available_tools=[],
    )

    assert attempts == 2
    assert decision.action is AutonomousDecisionAction.INVOKE_TOOL
    assert decision.selected_tool == "run_command"


@pytest.mark.asyncio
async def test_openai_autonomous_decision_engine_fails_after_retry_budget(monkeypatch) -> None:
    engine = OpenAIAutonomousDecisionEngine(client=object(), model="test-model")
    attempts = 0

    async def fake_request(prompt_payload: dict[str, object]):
        nonlocal attempts
        attempts += 1
        raise asyncio.TimeoutError()

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(engine, "_request_completion", fake_request)
    monkeypatch.setattr("harness.autonomous.decision_engine.asyncio.sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        await engine.decide(
            run=_Dumpable(),
            coding_session=_Dumpable(),
            available_tools=[],
        )

    assert attempts == 3

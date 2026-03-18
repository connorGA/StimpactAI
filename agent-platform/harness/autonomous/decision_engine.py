from __future__ import annotations

import json
from typing import Protocol

from openai import AsyncOpenAI

from api.core.config import get_openai_autonomous_model
from harness.schemas.autonomous import (
    AutonomousDecision,
    AutonomousDecisionAction,
    AutonomousRepairRunRecord,
    AutonomousRunEvent,
)
from harness.schemas.orchestrator import HarnessSessionSnapshot


class AutonomousDecisionEngine(Protocol):
    async def decide(
        self,
        *,
        run: AutonomousRepairRunRecord,
        coding_session: HarnessSessionSnapshot,
        available_tools: list[dict[str, object]],
        last_tool_result: dict[str, object] | None = None,
        recent_events: list[AutonomousRunEvent] | None = None,
    ) -> AutonomousDecision: ...


class OpenAIAutonomousDecisionEngine:
    def __init__(self, *, client: AsyncOpenAI, model: str | None = None) -> None:
        self._client = client
        self._model = model or get_openai_autonomous_model()

    async def decide(
        self,
        *,
        run: AutonomousRepairRunRecord,
        coding_session: HarnessSessionSnapshot,
        available_tools: list[dict[str, object]],
        last_tool_result: dict[str, object] | None = None,
        recent_events: list[AutonomousRunEvent] | None = None,
    ) -> AutonomousDecision:
        prompt_payload = {
            "run": run.model_dump(mode="json"),
            "coding_session": coding_session.model_dump(mode="json"),
            "available_tools": available_tools,
            "last_tool_result": last_tool_result or {},
            "recent_events": [event.model_dump(mode="json") for event in (recent_events or [])],
        }
        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the bounded decision-maker for an autonomous repair runner. "
                        "You must choose only from the provided tools and never invent new tools. "
                        "Prefer a disciplined workflow: inspect first, edit only when necessary, verify explicitly, "
                        "and recover to the checkpoint when execution failures suggest the working tree is unreliable. "
                        "Return raw JSON with keys: summary, rationale, action, selected_tool, arguments, "
                        "arguments_summary, feature_id, verification_kind. "
                        "Use action=invoke_tool to make the next tool call, action=complete only when the feature "
                        "verification state proves the objective is done, and action=fail only when the run "
                        "cannot safely continue."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload, indent=2, sort_keys=True),
                },
            ],
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned an empty autonomous decision.")
        decision = AutonomousDecision.model_validate_json(_extract_json_object(content))
        if decision.action is AutonomousDecisionAction.INVOKE_TOOL and not decision.selected_tool:
            raise ValueError("Autonomous decision must include selected_tool when invoking a tool.")
        return decision


def _extract_json_object(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        return normalized

    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in autonomous decision response.")
    return normalized[start : end + 1]

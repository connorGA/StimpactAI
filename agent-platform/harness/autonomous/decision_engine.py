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
                        "Each available tool may include arguments_schema, argument_examples, and usage_notes; "
                        "treat those as the source of truth for argument names and shapes. "
                        "Prefer a disciplined workflow: inspect first, edit only when necessary, verify explicitly, "
                        "and recover to the checkpoint when execution failures suggest the working tree is unreliable. "
                        "Use any relevant available tool, including repository command execution, to install, reproduce, "
                        "verify, inspect failures, and retry fixes. "
                        "If a tool call or verification fails, prefer investigating the failure and trying again over "
                        "giving up immediately unless the run is clearly blocked or unsafe. "
                        "When a tool validation error says fields are missing, extra, or invalid, adapt the next tool "
                        "arguments to match the provided schema instead of repeating the same call. "
                        "Only set verification_kind when the tool call is the actual feature verification step; "
                        "diagnostic probes like environment inspection or interpreter discovery must not be labeled as verification. "
                        "Do not mask verification failures with shell patterns like `|| true`, `; true`, or `&& true`; "
                        "run diagnostics separately from the command that is meant to count as verification. "
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
        decision = AutonomousDecision.model_validate(_extract_json_object(content))
        if decision.action is AutonomousDecisionAction.INVOKE_TOOL and not decision.selected_tool:
            raise ValueError("Autonomous decision must include selected_tool when invoking a tool.")
        return decision


def _extract_json_object(content: str) -> dict[str, object]:
    normalized = content.strip()
    start = normalized.find("{")
    if start == -1:
        raise ValueError("No JSON object found in autonomous decision response.")
    decoder = json.JSONDecoder()
    try:
        parsed, end = decoder.raw_decode(normalized[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("No valid JSON object found in autonomous decision response.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Autonomous decision response must begin with a JSON object.")
    return parsed

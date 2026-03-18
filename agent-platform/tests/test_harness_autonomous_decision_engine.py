from __future__ import annotations

from harness.autonomous.decision_engine import _extract_json_object


def test_extract_json_object_ignores_trailing_text_after_first_object() -> None:
    content = '{"summary":"inspect","rationale":"ok","action":"fail","selected_tool":null,"arguments":{},"arguments_summary":null,"feature_id":null,"verification_kind":null}\nextra text'

    extracted = _extract_json_object(content)

    assert extracted == {
        "summary": "inspect",
        "rationale": "ok",
        "action": "fail",
        "selected_tool": None,
        "arguments": {},
        "arguments_summary": None,
        "feature_id": None,
        "verification_kind": None,
    }

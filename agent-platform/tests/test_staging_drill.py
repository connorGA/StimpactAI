from __future__ import annotations

import json
from pathlib import Path

from staging_drill import (
    _build_benchmark_manifest,
    _build_benchmark_result,
    _build_benchmark_summary,
    _seed_drill_fixture,
)


def test_seed_drill_fixture_writes_expected_buggy_retry_files(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()
    (fixture_dir / "buggy_retry.py").write_text("print('stale')\n", encoding="utf-8")

    scenario = _seed_drill_fixture(str(tmp_path))

    assert scenario.name == "header-key"
    assert (fixture_dir / "__init__.py").read_text(encoding="utf-8") == ""
    assert (fixture_dir / "buggy_retry.py").read_text(encoding="utf-8") == (
        "def read_retry_after(headers: dict[str, str]) -> int:\n"
        "    value = headers[\"retry_after_seconds\"]\n"
        "    return int(value)\n"
    )
    assert (fixture_dir / "test_buggy_retry.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.buggy_retry import read_retry_after\n\n\n"
        "def test_read_retry_after_uses_standard_header() -> None:\n"
        "    headers = {\"Retry-After\": \"7\"}\n"
        "    assert read_retry_after(headers) == 7\n"
    )


def test_seed_drill_fixture_supports_alternate_parse_digit_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="parse-digit")

    assert scenario.name == "parse-digit"
    assert (fixture_dir / "buggy_retry.py").read_text(encoding="utf-8") == (
        "def parse_retry_after(value: str) -> int:\n"
        "    return int(value[1:])\n"
    )
    assert (fixture_dir / "test_buggy_retry.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.buggy_retry import parse_retry_after\n\n\n"
        "def test_parse_retry_after_keeps_the_full_number() -> None:\n"
        "    assert parse_retry_after(\"15\") == 15\n"
    )


def test_seed_drill_fixture_supports_imported_header_constant_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="imported-header-constant")

    assert scenario.name == "imported-header-constant"
    assert scenario.difficulty == "medium"
    assert (fixture_dir / "constants.py").read_text(encoding="utf-8") == (
        'RETRY_AFTER_HEADER = "retry_after_seconds"\n'
    )
    assert (fixture_dir / "buggy_retry.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.constants import RETRY_AFTER_HEADER\n\n\n"
        "def read_retry_after(headers: dict[str, str]) -> int:\n"
        "    return int(headers[RETRY_AFTER_HEADER])\n"
    )


def test_seed_drill_fixture_supports_cascading_retry_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="cascading-retry")

    assert scenario.name == "cascading-retry"
    assert scenario.difficulty == "hard"
    assert (fixture_dir / "policy.py").read_text(encoding="utf-8") == (
        "def should_retry(status_code: int) -> bool:\n"
        "    return status_code >= 500\n"
    )
    assert "test_should_retry_http_429" in (fixture_dir / "test_buggy_retry.py").read_text(encoding="utf-8")


def test_seed_drill_fixture_supports_misleading_stacktrace_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="misleading-stacktrace")

    assert scenario.name == "misleading-stacktrace"
    assert scenario.difficulty == "hard"
    assert (fixture_dir / "api.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.headers import read_retry_after\n\n\n"
        "def handle_retry_after(headers: dict[str, str]) -> int:\n"
        "    return read_retry_after(headers)\n"
    )


def test_seed_drill_fixture_supports_wide_search_space_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="wide-search-space")

    assert scenario.name == "wide-search-space"
    assert scenario.difficulty == "hard"
    assert (fixture_dir / "selectors.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.retry_matrix import TRANSIENT_STATUSES\n\n\n"
        "def retryable_statuses() -> set[int]:\n"
        "    return {status for status in TRANSIENT_STATUSES if status != 429}\n"
    )


def test_seed_drill_fixture_supports_misleading_cascade_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="misleading-cascade")

    assert scenario.name == "misleading-cascade"
    assert scenario.difficulty == "very-hard"
    assert "build_retry_response" in (fixture_dir / "api.py").read_text(encoding="utf-8")
    assert "test_build_retry_response_retries_http_429" in (
        fixture_dir / "test_buggy_retry.py"
    ).read_text(encoding="utf-8")


def test_build_benchmark_manifest_includes_status_429_scenario() -> None:
    manifest = _build_benchmark_manifest()

    scenario_ids = {item["scenario_id"] for item in manifest["scenarios"]}
    assert manifest["schema_version"] == 1
    assert "status-429" in scenario_ids
    assert "imported-header-constant" in scenario_ids
    assert "cascading-retry" in scenario_ids
    assert "misleading-stacktrace" in scenario_ids
    assert "wide-search-space" in scenario_ids
    assert "misleading-cascade" in scenario_ids


def test_build_benchmark_result_uses_outcome_success_flags(tmp_path: Path) -> None:
    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="status-429")
    result = _build_benchmark_result(
        scenario=scenario,
        final_run_detail={
            "run": {
                "id": "run-1",
                "status": "succeeded",
                "phase": "completed",
            },
            "outcome": {
                "total_steps": 4,
                "recovery_attempts": 1,
                "stagnation_count": 0,
                "fresh_verification_satisfied": True,
                "failure_class": None,
                "final_success": True,
            },
        },
        repository_root="/tmp/repo",
    )

    assert json.loads(json.dumps(result))["scenario_id"] == "status-429"
    assert result["bug_class"] == "retry-policy-429"
    assert result["difficulty"] == "easy"
    assert result["challenge_tags"] == ["single-file", "policy-logic"]
    assert result["final_success"] is True


def test_build_benchmark_summary_uses_latest_result_per_scenario(tmp_path: Path) -> None:
    first = tmp_path / "header-key-old.json"
    first.write_text(
        json.dumps(
            {
                "scenario_id": "header-key",
                "bug_class": "retry-after-header",
                "status": "failed",
                "final_success": False,
                "total_steps": 3,
            }
        ),
        encoding="utf-8",
    )
    second = tmp_path / "header-key-new.json"
    second.write_text(
        json.dumps(
            {
                "scenario_id": "header-key",
                "bug_class": "retry-after-header",
                "status": "succeeded",
                "final_success": True,
                "total_steps": 6,
            }
        ),
        encoding="utf-8",
    )
    third = tmp_path / "cascading-retry.json"
    third.write_text(
        json.dumps(
            {
                "scenario_id": "cascading-retry",
                "bug_class": "cascading-retry-bugs",
                "difficulty": "hard",
                "challenge_tags": ["multi-file", "iterative-repair"],
                "status": "succeeded",
                "final_success": True,
                "total_steps": 9,
            }
        ),
        encoding="utf-8",
    )

    first.touch()
    second.touch()
    third.touch()

    summary = _build_benchmark_summary(str(tmp_path))

    assert summary["scenario_count"] == 2
    assert summary["successful_scenarios"] == 2
    assert summary["success_rate"] == 1.0
    by_difficulty = {entry["difficulty"]: entry for entry in summary["by_difficulty"]}
    assert by_difficulty["easy"]["total"] == 1
    assert by_difficulty["easy"]["average_steps"] == 6.0
    assert by_difficulty["hard"]["total"] == 1
    scenarios = {entry["scenario_id"]: entry for entry in summary["scenarios"]}
    assert scenarios["header-key"]["status"] == "succeeded"

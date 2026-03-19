from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from datetime import UTC, datetime
from typing import Any
from urllib import error, parse, request


@dataclass(frozen=True)
class DrillScenario:
    name: str
    bug_class: str
    error_summary: str
    stacktrace: str
    request_path: str
    response_status_code: int
    fixture_files: dict[str, str]


_BASE_FIXTURE_FILES = {
    "staging_drill_fixture/__init__.py": "",
}

_DRILL_SCENARIOS: dict[str, DrillScenario] = {
    "header-key": DrillScenario(
        name="header-key",
        bug_class="retry-after-header",
        error_summary="Retry-After header handling raised KeyError retry_after_seconds",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/buggy_retry.py", line 2, in read_retry_after\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-after",
        response_status_code=503,
        fixture_files={
            "staging_drill_fixture/buggy_retry.py": (
                "def read_retry_after(headers: dict[str, str]) -> int:\n"
                '    value = headers["retry_after_seconds"]\n'
                "    return int(value)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.buggy_retry import read_retry_after\n\n\n"
                "def test_read_retry_after_uses_standard_header() -> None:\n"
                '    headers = {"Retry-After": "7"}\n'
                "    assert read_retry_after(headers) == 7\n"
            ),
        },
    ),
    "parse-digit": DrillScenario(
        name="parse-digit",
        bug_class="retry-after-parse",
        error_summary="Retry-After parsing dropped the first digit",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/test_buggy_retry.py", line 5, in '
            "test_parse_retry_after_keeps_the_full_number\n"
            "AssertionError: expected 15 seconds but parsed 5"
        ),
        request_path="/retry-after/parse",
        response_status_code=503,
        fixture_files={
            "staging_drill_fixture/buggy_retry.py": (
                "def parse_retry_after(value: str) -> int:\n"
                "    return int(value[1:])\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.buggy_retry import parse_retry_after\n\n\n"
                "def test_parse_retry_after_keeps_the_full_number() -> None:\n"
                '    assert parse_retry_after("15") == 15\n'
            ),
        },
    ),
    "status-429": DrillScenario(
        name="status-429",
        bug_class="retry-policy-429",
        error_summary="Retry policy skipped HTTP 429",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/test_buggy_retry.py", line 5, in '
            "test_should_retry_http_429\n"
            "AssertionError: expected HTTP 429 to be retried"
        ),
        request_path="/retry-policy",
        response_status_code=429,
        fixture_files={
            "staging_drill_fixture/buggy_retry.py": (
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code >= 500\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.buggy_retry import should_retry\n\n\n"
                "def test_should_retry_http_429() -> None:\n"
                "    assert should_retry(429) is True\n"
            ),
        },
    ),
}


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {body}") from exc
    return json.loads(body) if body else {}


def _poll_json(url: str, *, timeout_seconds: int, interval_seconds: float) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            return _http_json("GET", url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(interval_seconds)
    raise RuntimeError(f"Timed out polling {url}: {last_error}")


def _current_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001
        return "staging-validation"


def _run_git(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()


def _prepare_repository_root(repository_root: str) -> None:
    root = Path(repository_root).expanduser().resolve()
    if not root.exists():
        raise RuntimeError(f"Repository root does not exist: {root}")
    if not (root / ".git").exists():
        raise RuntimeError(f"Repository root is not a git checkout: {root}")

    branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _run_git(root, "fetch", "origin", branch)
    _run_git(root, "reset", "--hard", "FETCH_HEAD")
    _run_git(root, "clean", "-fd")


def _seed_drill_fixture(repository_root: str, *, scenario_name: str = "header-key") -> DrillScenario:
    root = Path(repository_root).expanduser().resolve()
    scenario = _DRILL_SCENARIOS[scenario_name]
    fixture_files = {
        **_BASE_FIXTURE_FILES,
        **scenario.fixture_files,
    }
    for relative_path, content in fixture_files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return scenario


def _build_benchmark_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_from": "staging_drill",
        "scenarios": [
            {
                "scenario_id": scenario.name,
                "bug_class": scenario.bug_class,
                "error_summary": scenario.error_summary,
                "request_path": scenario.request_path,
                "response_status_code": scenario.response_status_code,
            }
            for scenario in _DRILL_SCENARIOS.values()
        ],
    }


def _build_benchmark_result(
    *,
    scenario: DrillScenario,
    final_run_detail: dict[str, Any],
    repository_root: str | None,
) -> dict[str, Any]:
    run = final_run_detail.get("run", {})
    outcome = final_run_detail.get("outcome", {}) or {}
    final_success = bool(outcome.get("final_success"))
    if not outcome:
        final_success = run.get("status") == "succeeded"
    return {
        "schema_version": 1,
        "scenario_id": scenario.name,
        "bug_class": scenario.bug_class,
        "repository_root": repository_root,
        "run_id": run.get("id"),
        "status": run.get("status"),
        "phase": run.get("phase"),
        "total_steps": outcome.get("total_steps"),
        "recovery_attempts": outcome.get("recovery_attempts"),
        "stagnation_count": outcome.get("stagnation_count"),
        "fresh_verification_satisfied": outcome.get("fresh_verification_satisfied"),
        "failure_class": outcome.get("failure_class"),
        "final_success": final_success,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a golden-path staging drill.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend API base URL.")
    parser.add_argument("--project-id", required=True, help="Project id used for telemetry and incident lookup.")
    parser.add_argument("--service", default="billing-api", help="Service name for the synthetic telemetry.")
    parser.add_argument("--environment", default="staging", help="Telemetry environment.")
    parser.add_argument("--repository-root", default=None, help="Repository root path for the autonomous run.")
    parser.add_argument(
        "--scenario",
        choices=sorted(_DRILL_SCENARIOS),
        default="header-key",
        help="Bug scenario to seed into the temporary repository checkout.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Overall drill timeout.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds.")
    parser.add_argument("--write-manifest", default=None, help="Optional path to write the scenario benchmark manifest.")
    parser.add_argument("--result-path", default=None, help="Optional path to write a machine-readable benchmark result.")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote the run after sandbox verification succeeds.",
    )
    args = parser.parse_args()

    scenario = _DRILL_SCENARIOS[args.scenario]
    if args.write_manifest:
        manifest_path = Path(args.write_manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(_build_benchmark_manifest(), indent=2), encoding="utf-8")
    if args.repository_root:
        _prepare_repository_root(args.repository_root)
        scenario = _seed_drill_fixture(args.repository_root, scenario_name=args.scenario)

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    error_message = f"{scenario.error_summary} {timestamp}"
    drill_started_at = datetime.now(UTC)
    telemetry_payload = {
        "project_id": args.project_id,
        "environment": args.environment,
        "service": args.service,
        "error_message": error_message,
        "stacktrace": scenario.stacktrace,
        "request": {"method": "POST", "path": scenario.request_path},
        "response": {"status_code": scenario.response_status_code},
        "commit_sha": _current_commit_sha(),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    accepted = _http_json("POST", f"{args.api_url}/telemetry/error", telemetry_payload)
    print(json.dumps({"telemetry": accepted}, indent=2))

    incidents_url = (
        f"{args.api_url}/incidents?"
        + parse.urlencode({"project_id": args.project_id, "limit": 20, "offset": 0})
    )
    deadline = time.time() + args.timeout_seconds
    incident = None
    while time.time() < deadline:
        listing = _http_json("GET", incidents_url)
        for candidate in listing.get("items", []):
            title = str(candidate.get("title", ""))
            created_at_raw = candidate.get("created_at")
            created_at = None
            if isinstance(created_at_raw, str):
                try:
                    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                except ValueError:
                    created_at = None
            if (
                candidate.get("service") == args.service
                and error_message in title
                and created_at is not None
                and created_at >= drill_started_at
            ):
                incident = candidate
                break
        if incident is not None:
            break
        time.sleep(args.poll_interval)
    if incident is None:
        raise RuntimeError("Timed out waiting for incident creation.")

    incident_id = incident["id"]
    run_payload = {
        "execution_mode": "repair_and_propose",
        "allow_writeback": True,
        "benchmark_scenario_id": scenario.name,
        "benchmark_bug_class": scenario.bug_class,
    }
    if args.repository_root:
        run_payload["repository_root"] = args.repository_root

    run = _http_json(
        "POST",
        f"{args.api_url}/incidents/{incident_id}/autonomous-runs",
        run_payload,
    )
    print(json.dumps({"incident_id": incident_id, "run_started": run}, indent=2))

    run_id = run["run"]["id"]
    run_detail_url = f"{args.api_url}/incidents/{incident_id}/autonomous-runs/{run_id}"

    latest_detail = None
    while time.time() < deadline:
        latest_detail = _http_json("GET", run_detail_url)
        approval_status = latest_detail["run"].get("approval_status")
        if approval_status == "pending":
            latest_detail = _http_json(
                "POST",
                f"{args.api_url}/incidents/{incident_id}/autonomous-runs/{run_id}/approval",
                {"approval_status": "approved"},
            )
        status = latest_detail["run"].get("status")
        promotion_status = latest_detail["run"].get("promotion_status")
        if status in {"failed", "cancelled"}:
            raise RuntimeError(json.dumps(latest_detail, indent=2))
        if args.promote and promotion_status == "ready":
            latest_detail = _http_json(
                "POST",
                f"{args.api_url}/incidents/{incident_id}/autonomous-runs/{run_id}/promote",
            )
            promotion_status = latest_detail["run"].get("promotion_status")
        if args.promote and promotion_status == "proposed":
            break
        if not args.promote and promotion_status in {"ready", "blocked", "proposed"}:
            break
        time.sleep(args.poll_interval)

    if latest_detail is None:
        raise RuntimeError("Timed out waiting for autonomous run completion.")

    print(json.dumps({"final_run_detail": latest_detail}, indent=2))
    if args.result_path:
        result_path = Path(args.result_path)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result = _build_benchmark_result(
            scenario=scenario,
            final_run_detail=latest_detail,
            repository_root=args.repository_root,
        )
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

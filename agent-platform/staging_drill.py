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
    difficulty: str
    error_summary: str
    stacktrace: str
    request_path: str
    response_status_code: int
    challenge_tags: tuple[str, ...]
    fixture_files: dict[str, str]


_BASE_FIXTURE_FILES = {
    "staging_drill_fixture/__init__.py": "",
}


def _frontend_drill_profile(*, url: str = "http://127.0.0.1:3000/frontend-drill") -> str:
    return (
        "start_command: npm --prefix client-ui run dev -- --hostname 127.0.0.1 --port 3000\n"
        "browser_verification_entrypoints:\n"
        "  - name: frontend-drill\n"
        f"    url: {url}\n"
        "    description: Frontend drill scenario page.\n"
        "    ready_selector: '[data-drill-root=\"frontend-drill\"]'\n"
        "environment_assumptions:\n"
        "  - Node.js and npm are available locally.\n"
        "  - The frontend drill route renders without depending on the backend API.\n"
        "ignored_directories:\n"
        "  - .git\n"
        "  - node_modules\n"
        "  - .next\n"
        "language_hints:\n"
        "  \".ts\": typescript\n"
        "  \".tsx\": typescript\n"
    )


_FRONTEND_DRILL_VERIFY_SCRIPT = """import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";

const EXPECTATIONS_PATH = ".stimpactai/frontend_drill_expectations.json";
const DEV_SERVER_COMMAND =
  "npm --prefix client-ui run dev -- --hostname 127.0.0.1 --port 3000";

async function fetchText(url) {
  const response = await fetch(url);
  return {
    statusCode: response.status,
    html: await response.text(),
  };
}

async function main() {
  const expectations = JSON.parse(await readFile(EXPECTATIONS_PATH, "utf-8"));
  if (!existsSync("client-ui/node_modules/next")) {
    throw new Error("Frontend dependencies are missing. Run npm install in the repository root and client-ui before verifying.");
  }
  const process = spawn(DEV_SERVER_COMMAND, {
    shell: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  let childError = null;
  process.stdout.on("data", (chunk) => {
    logs += String(chunk);
  });
  process.stderr.on("data", (chunk) => {
    logs += String(chunk);
  });
  process.on("error", (error) => {
    childError = error;
  });

  try {
    const deadline = Date.now() + 120_000;
    let html = "";
    let statusCode = null;

    while (Date.now() < deadline) {
      try {
        const response = await fetchText(expectations.url);
        statusCode = response.statusCode;
        html = response.html;
      } catch {
        statusCode = null;
        html = "";
      }

      if (childError) {
        throw childError;
      }
      if (process.exitCode !== null) {
        throw new Error(
          logs.trim() || `Frontend dev server exited before the drill page became ready (exit ${process.exitCode}).`,
        );
      }

      if (statusCode === 200 && html.includes(expectations.ready_marker)) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }

    if (!(statusCode === 200 && html.includes(expectations.ready_marker))) {
      throw new Error("Frontend drill page did not become ready before timeout.");
    }

    const missing = expectations.contains_text.filter((snippet) => !html.includes(snippet));
    const forbidden = expectations.not_contains_text.filter((snippet) => html.includes(snippet));
    if (missing.length > 0 || forbidden.length > 0) {
      throw new Error(
        JSON.stringify(
          {
            missing,
            forbidden,
            status_code: statusCode,
          },
          null,
          2,
        ),
      );
    }
  } finally {
    process.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
"""


def _frontend_drill_support_files(
    *,
    contains_text: list[str],
    not_contains_text: list[str] | None = None,
) -> dict[str, str]:
    expectations = {
        "url": "http://127.0.0.1:3000/frontend-drill",
        "ready_marker": 'data-drill-root="frontend-drill"',
        "contains_text": contains_text,
        "not_contains_text": not_contains_text or [],
    }
    return {
        ".stimpactai/profile.yml": _frontend_drill_profile(),
        ".stimpactai/frontend_drill_expectations.json": json.dumps(expectations, indent=2),
        "frontend_drill_verify.mjs": _FRONTEND_DRILL_VERIFY_SCRIPT,
    }


_DRILL_SCENARIOS: dict[str, DrillScenario] = {
    "header-key": DrillScenario(
        name="header-key",
        bug_class="retry-after-header",
        difficulty="easy",
        error_summary="Retry-After header handling raised KeyError retry_after_seconds",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/buggy_retry.py", line 2, in read_retry_after\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-after",
        response_status_code=503,
        challenge_tags=("single-file", "direct-stacktrace"),
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
        difficulty="easy",
        error_summary="Retry-After parsing dropped the first digit",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/test_buggy_retry.py", line 5, in '
            "test_parse_retry_after_keeps_the_full_number\n"
            "AssertionError: expected 15 seconds but parsed 5"
        ),
        request_path="/retry-after/parse",
        response_status_code=503,
        challenge_tags=("single-file", "deterministic-test"),
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
        difficulty="easy",
        error_summary="Retry policy skipped HTTP 429",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/test_buggy_retry.py", line 5, in '
            "test_should_retry_http_429\n"
            "AssertionError: expected HTTP 429 to be retried"
        ),
        request_path="/retry-policy",
        response_status_code=429,
        challenge_tags=("single-file", "policy-logic"),
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
    "imported-header-constant": DrillScenario(
        name="imported-header-constant",
        bug_class="imported-header-constant",
        difficulty="medium",
        error_summary="Retry-After lookup used a stale imported constant",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/buggy_retry.py", line 5, in read_retry_after\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-after/imported-constant",
        response_status_code=503,
        challenge_tags=("multi-file", "imported-helper", "indirect-root-cause"),
        fixture_files={
            "staging_drill_fixture/constants.py": 'RETRY_AFTER_HEADER = "retry_after_seconds"\n',
            "staging_drill_fixture/buggy_retry.py": (
                "from staging_drill_fixture.constants import RETRY_AFTER_HEADER\n\n\n"
                "def read_retry_after(headers: dict[str, str]) -> int:\n"
                "    return int(headers[RETRY_AFTER_HEADER])\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.buggy_retry import read_retry_after\n\n\n"
                "def test_read_retry_after_uses_standard_header() -> None:\n"
                '    headers = {"Retry-After": "7"}\n'
                "    assert read_retry_after(headers) == 7\n"
            ),
        },
    ),
    "cascading-retry": DrillScenario(
        name="cascading-retry",
        bug_class="cascading-retry-bugs",
        difficulty="hard",
        error_summary="Retry pipeline still failed after the first apparent fix",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/buggy_retry.py", line 5, in read_retry_after\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-pipeline/cascading",
        response_status_code=503,
        challenge_tags=("multi-file", "iterative-repair", "multiple-failures"),
        fixture_files={
            "staging_drill_fixture/constants.py": 'RETRY_AFTER_HEADER = "retry_after_seconds"\n',
            "staging_drill_fixture/policy.py": (
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code >= 500\n"
            ),
            "staging_drill_fixture/buggy_retry.py": (
                "from staging_drill_fixture.constants import RETRY_AFTER_HEADER\n"
                "from staging_drill_fixture.policy import should_retry\n\n\n"
                "def read_retry_after(headers: dict[str, str]) -> int:\n"
                "    return int(headers[RETRY_AFTER_HEADER])\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.buggy_retry import read_retry_after, should_retry\n\n\n"
                "def test_read_retry_after_uses_standard_header() -> None:\n"
                '    headers = {"Retry-After": "7"}\n'
                "    assert read_retry_after(headers) == 7\n\n\n"
                "def test_should_retry_http_429() -> None:\n"
                "    assert should_retry(429) is True\n\n\n"
                "def test_should_retry_http_500_still_retries() -> None:\n"
                "    assert should_retry(500) is True\n"
            ),
        },
    ),
    "misleading-stacktrace": DrillScenario(
        name="misleading-stacktrace",
        bug_class="misleading-stacktrace-helper",
        difficulty="hard",
        error_summary="Retry handler failed in the request wrapper",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/api.py", line 5, in handle_retry_after\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-after/misleading",
        response_status_code=503,
        challenge_tags=("misleading-stacktrace", "multi-file", "wrapper-indirection"),
        fixture_files={
            "staging_drill_fixture/constants.py": 'RETRY_AFTER_HEADER = "Retry-After"\n',
            "staging_drill_fixture/headers.py": (
                "from staging_drill_fixture.constants import RETRY_AFTER_HEADER\n\n\n"
                "def read_retry_after(headers: dict[str, str]) -> int:\n"
                '    return int(headers["retry_after_seconds"])\n'
            ),
            "staging_drill_fixture/api.py": (
                "from staging_drill_fixture.headers import read_retry_after\n\n\n"
                "def handle_retry_after(headers: dict[str, str]) -> int:\n"
                "    return read_retry_after(headers)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.api import handle_retry_after\n\n\n"
                "def test_handle_retry_after_uses_standard_header() -> None:\n"
                '    headers = {"Retry-After": "9"}\n'
                "    assert handle_retry_after(headers) == 9\n"
            ),
        },
    ),
    "wide-search-space": DrillScenario(
        name="wide-search-space",
        bug_class="wide-search-space-policy",
        difficulty="hard",
        error_summary="Retry policy lookup skipped HTTP 429 in the service layer",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/service.py", line 5, in should_retry_request\n'
            "AssertionError: expected HTTP 429 to be retried"
        ),
        request_path="/retry-policy/wide-search",
        response_status_code=429,
        challenge_tags=("wide-search-space", "multi-file", "decoy-modules"),
        fixture_files={
            "staging_drill_fixture/legacy_policy.py": (
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code in {500, 502, 503, 504}\n"
            ),
            "staging_drill_fixture/retry_matrix.py": (
                "TRANSIENT_STATUSES = {429, 500, 502, 503, 504}\n"
            ),
            "staging_drill_fixture/selectors.py": (
                "from staging_drill_fixture.retry_matrix import TRANSIENT_STATUSES\n\n\n"
                "def retryable_statuses() -> set[int]:\n"
                "    return {status for status in TRANSIENT_STATUSES if status != 429}\n"
            ),
            "staging_drill_fixture/policy.py": (
                "from staging_drill_fixture.selectors import retryable_statuses\n\n\n"
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code in retryable_statuses()\n"
            ),
            "staging_drill_fixture/service.py": (
                "from staging_drill_fixture.policy import should_retry\n\n\n"
                "def should_retry_request(status_code: int) -> bool:\n"
                "    return should_retry(status_code)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.service import should_retry_request\n\n\n"
                "def test_should_retry_http_429() -> None:\n"
                "    assert should_retry_request(429) is True\n\n\n"
                "def test_should_retry_http_500() -> None:\n"
                "    assert should_retry_request(500) is True\n"
            ),
        },
    ),
    "misleading-cascade": DrillScenario(
        name="misleading-cascade",
        bug_class="misleading-cascade-bugs",
        difficulty="very-hard",
        error_summary="Retry API still failed after the first apparent fix",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/api.py", line 6, in build_retry_response\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-pipeline/misleading-cascade",
        response_status_code=503,
        challenge_tags=("misleading-stacktrace", "iterative-repair", "multi-file", "multiple-failures"),
        fixture_files={
            "staging_drill_fixture/constants.py": 'RETRY_AFTER_HEADER = "retry_after_seconds"\n',
            "staging_drill_fixture/policy.py": (
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code >= 500\n"
            ),
            "staging_drill_fixture/api.py": (
                "from staging_drill_fixture.constants import RETRY_AFTER_HEADER\n"
                "from staging_drill_fixture.policy import should_retry\n\n\n"
                "def build_retry_response(headers: dict[str, str], status_code: int) -> tuple[int, bool]:\n"
                "    retry_after = int(headers[RETRY_AFTER_HEADER])\n"
                "    return retry_after, should_retry(status_code)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.api import build_retry_response\n\n\n"
                "def test_build_retry_response_uses_standard_header() -> None:\n"
                '    assert build_retry_response({"Retry-After": "11"}, 500)[0] == 11\n\n\n'
                "def test_build_retry_response_retries_http_429() -> None:\n"
                '    assert build_retry_response({"Retry-After": "11"}, 429)[1] is True\n\n\n'
                "def test_build_retry_response_still_retries_http_500() -> None:\n"
                '    assert build_retry_response({"Retry-After": "11"}, 500)[1] is True\n'
            ),
        },
    ),
    "env-config-mismatch": DrillScenario(
        name="env-config-mismatch",
        bug_class="env-config-mismatch",
        difficulty="hard",
        error_summary="Retry policy default config skipped HTTP 429",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/service.py", line 5, in should_retry_request\n'
            "AssertionError: expected HTTP 429 to be retried from default config"
        ),
        request_path="/retry-policy/env-config",
        response_status_code=429,
        challenge_tags=("env-config", "multi-file", "default-behavior"),
        fixture_files={
            "staging_drill_fixture/config.py": (
                "import os\n\n\n"
                "def retry_statuses_from_env() -> set[int]:\n"
                '    raw = os.getenv("RETRY_STATUSES", "500,502,503,504")\n'
                "    return {int(value.strip()) for value in raw.split(\",\") if value.strip()}\n"
            ),
            "staging_drill_fixture/policy.py": (
                "from staging_drill_fixture.config import retry_statuses_from_env\n\n\n"
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code in retry_statuses_from_env()\n"
            ),
            "staging_drill_fixture/service.py": (
                "from staging_drill_fixture.policy import should_retry\n\n\n"
                "def should_retry_request(status_code: int) -> bool:\n"
                "    return should_retry(status_code)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.service import should_retry_request\n\n\n"
                "def test_should_retry_http_429_from_default_config() -> None:\n"
                "    assert should_retry_request(429) is True\n\n\n"
                "def test_should_retry_http_500_from_default_config() -> None:\n"
                "    assert should_retry_request(500) is True\n"
            ),
        },
    ),
    "env-misleading-cascade": DrillScenario(
        name="env-misleading-cascade",
        bug_class="env-misleading-cascade",
        difficulty="very-hard",
        error_summary="Retry response still failed after the config-backed fix",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/service.py", line 6, in build_retry_response\n'
            "KeyError: 'retry_after_seconds'"
        ),
        request_path="/retry-response/env-misleading-cascade",
        response_status_code=503,
        challenge_tags=("env-config", "misleading-stacktrace", "iterative-repair", "multiple-failures"),
        fixture_files={
            "staging_drill_fixture/config.py": (
                "import os\n\n\n"
                "def retry_statuses_from_env() -> set[int]:\n"
                '    raw = os.getenv("RETRY_STATUSES", "500,502,503,504")\n'
                "    return {int(value.strip()) for value in raw.split(\",\") if value.strip()}\n\n\n"
                "def retry_after_header() -> str:\n"
                '    return os.getenv("RETRY_AFTER_HEADER", "retry_after_seconds")\n'
            ),
            "staging_drill_fixture/service.py": (
                "from staging_drill_fixture.config import retry_after_header, retry_statuses_from_env\n\n\n"
                "def build_retry_response(headers: dict[str, str], status_code: int) -> tuple[int, bool]:\n"
                "    retry_after = int(headers[retry_after_header()])\n"
                "    return retry_after, status_code in retry_statuses_from_env()\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.service import build_retry_response\n\n\n"
                "def test_build_retry_response_uses_standard_header() -> None:\n"
                '    assert build_retry_response({"Retry-After": "12"}, 500)[0] == 12\n\n\n'
                "def test_build_retry_response_retries_http_429() -> None:\n"
                '    assert build_retry_response({"Retry-After": "12"}, 429)[1] is True\n\n\n'
                "def test_build_retry_response_still_retries_http_500() -> None:\n"
                '    assert build_retry_response({"Retry-After": "12"}, 500)[1] is True\n'
            ),
        },
    ),
    "wrong-first-fix-pressure": DrillScenario(
        name="wrong-first-fix-pressure",
        bug_class="wrong-first-fix-pressure",
        difficulty="very-hard",
        error_summary="Retry response still failed after the first plausible parser fix",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/api.py", line 6, in build_retry_response\n'
            "AssertionError: expected Retry-After 15 but got 5"
        ),
        request_path="/retry-response/wrong-first-fix",
        response_status_code=503,
        challenge_tags=("wrong-first-fix", "iterative-repair", "misleading-stacktrace", "multiple-failures"),
        fixture_files={
            "staging_drill_fixture/parser.py": (
                "def parse_retry_after(value: str) -> int:\n"
                "    return int(value[1:])\n"
            ),
            "staging_drill_fixture/policy.py": (
                "def should_retry(status_code: int) -> bool:\n"
                "    return status_code >= 500\n"
            ),
            "staging_drill_fixture/api.py": (
                "from staging_drill_fixture.parser import parse_retry_after\n"
                "from staging_drill_fixture.policy import should_retry\n\n\n"
                "def build_retry_response(headers: dict[str, str], status_code: int) -> tuple[int, bool]:\n"
                '    retry_after = parse_retry_after(headers["Retry-After"])\n'
                "    return retry_after, should_retry(status_code)\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.api import build_retry_response\n\n\n"
                "def test_build_retry_response_keeps_full_retry_delay() -> None:\n"
                '    assert build_retry_response({"Retry-After": "15"}, 500)[0] == 15\n\n\n'
                "def test_build_retry_response_retries_http_429() -> None:\n"
                '    assert build_retry_response({"Retry-After": "15"}, 429)[1] is True\n\n\n'
                "def test_build_retry_response_still_retries_http_500() -> None:\n"
                '    assert build_retry_response({"Retry-After": "15"}, 500)[1] is True\n'
            ),
        },
    ),
    "decoy-config-fallback": DrillScenario(
        name="decoy-config-fallback",
        bug_class="decoy-config-fallback",
        difficulty="hard",
        error_summary="Retry selector used legacy defaults when no env override was present",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/staging_drill_fixture/service.py", line 5, in should_retry_request\n'
            "AssertionError: expected HTTP 429 to be retried from configured defaults"
        ),
        request_path="/retry-policy/decoy-config",
        response_status_code=429,
        challenge_tags=("env-config", "wide-search-space", "decoy-config"),
        fixture_files={
            "staging_drill_fixture/defaults.py": (
                "DEFAULT_RETRY_STATUSES = {429, 500, 502, 503, 504}\n"
                "LEGACY_RETRY_STATUSES = {500, 502, 503, 504}\n"
            ),
            "staging_drill_fixture/config.py": (
                "import os\n\n"
                "from staging_drill_fixture.defaults import DEFAULT_RETRY_STATUSES, LEGACY_RETRY_STATUSES\n\n\n"
                "def configured_retry_statuses() -> set[int]:\n"
                '    raw = os.getenv("RETRY_STATUSES")\n'
                "    if raw:\n"
                "        return {int(value.strip()) for value in raw.split(\",\") if value.strip()}\n"
                "    return LEGACY_RETRY_STATUSES\n"
            ),
            "staging_drill_fixture/selectors.py": (
                "from staging_drill_fixture.config import configured_retry_statuses\n\n\n"
                "def retryable_statuses() -> set[int]:\n"
                "    return configured_retry_statuses()\n"
            ),
            "staging_drill_fixture/service.py": (
                "from staging_drill_fixture.selectors import retryable_statuses\n\n\n"
                "def should_retry_request(status_code: int) -> bool:\n"
                "    return status_code in retryable_statuses()\n"
            ),
            "staging_drill_fixture/test_buggy_retry.py": (
                "from staging_drill_fixture.service import should_retry_request\n\n\n"
                "def test_should_retry_http_429_from_defaults() -> None:\n"
                "    assert should_retry_request(429) is True\n\n\n"
                "def test_should_retry_http_500_from_defaults() -> None:\n"
                "    assert should_retry_request(500) is True\n"
            ),
        },
    ),
    "frontend-live-status-copy": DrillScenario(
        name="frontend-live-status-copy",
        bug_class="frontend-live-status-copy",
        difficulty="hard",
        error_summary="Frontend live status summary reported healthy state while an open incident was visible",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/client-ui/src/app/frontend-drill/page.tsx", line 13, in FrontendDrillPage\n'
            "AssertionError: expected the page headline to show an active incident warning"
        ),
        request_path="/frontend-drill/live-status",
        response_status_code=503,
        challenge_tags=("client-ui", "copy-logic", "helper-indirection"),
        fixture_files={
            **_frontend_drill_support_files(
                contains_text=["1 active incident needs attention"],
                not_contains_text=["All monitored services look healthy"],
            ),
            "client-ui/src/lib/frontend-drill/live-status.ts": (
                "export function buildLiveStatusTitle(openIncidentCount: number): string {\n"
                "  if (openIncidentCount <= 1) {\n"
                '    return "All monitored services look healthy";\n'
                "  }\n\n"
                '  return `${openIncidentCount} active incidents need attention`;\n'
                "}\n"
            ),
            "client-ui/src/app/frontend-drill/page.tsx": (
                'import { buildLiveStatusTitle } from "@/lib/frontend-drill/live-status";\n\n'
                "const incidents = [\n"
                '  { id: "inc-1", status: "open", title: "Checkout API latency spike" },\n'
                '  { id: "inc-2", status: "resolved", title: "Background queue caught up" },\n'
                "];\n\n"
                "export default function FrontendDrillPage() {\n"
                '  const openIncidentCount = incidents.filter((incident) => incident.status === "open").length;\n'
                "  return (\n"
                '    <main data-drill-root="frontend-drill" className="space-y-4 p-8">\n'
                '      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8f735c]">Frontend drill</p>\n'
                '      <h1 className="text-3xl font-semibold text-[#171717]">{buildLiveStatusTitle(openIncidentCount)}</h1>\n'
                '      <p className="text-sm text-[#5f6470]">{incidents[0].title}</p>\n'
                "    </main>\n"
                "  );\n"
                "}\n"
            ),
        },
    ),
    "frontend-empty-state-filter": DrillScenario(
        name="frontend-empty-state-filter",
        bug_class="frontend-empty-state-filter",
        difficulty="hard",
        error_summary="Frontend incident board rendered an empty state even though an open incident was present",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/client-ui/src/app/frontend-drill/page.tsx", line 18, in FrontendDrillPage\n'
            'AssertionError: expected "Checkout API latency spike" to remain visible'
        ),
        request_path="/frontend-drill/empty-state",
        response_status_code=503,
        challenge_tags=("client-ui", "wide-search-space", "decoy-modules"),
        fixture_files={
            **_frontend_drill_support_files(
                contains_text=["Checkout API latency spike"],
                not_contains_text=["No active incidents in the drill board."],
            ),
            "client-ui/src/lib/frontend-drill/legacy-selectors.ts": (
                "export function keepAllIncidentIds(ids: string[]): string[] {\n"
                "  return ids;\n"
                "}\n"
            ),
            "client-ui/src/lib/frontend-drill/selectors.ts": (
                'type DrillIncident = { id: string; status: "open" | "resolved"; title: string };\n\n'
                "export function visibleFrontendIncidents(incidents: DrillIncident[]): DrillIncident[] {\n"
                '  return incidents.filter((incident) => incident.status !== "open");\n'
                "}\n"
            ),
            "client-ui/src/app/frontend-drill/page.tsx": (
                'import { visibleFrontendIncidents } from "@/lib/frontend-drill/selectors";\n\n'
                "const incidents = [\n"
                '  { id: "inc-1", status: "open" as const, title: "Checkout API latency spike" },\n'
                '  { id: "inc-2", status: "resolved" as const, title: "Notification worker recovered" },\n'
                "];\n\n"
                "export default function FrontendDrillPage() {\n"
                "  const visibleIncidents = visibleFrontendIncidents(incidents);\n"
                "  return (\n"
                '    <main data-drill-root="frontend-drill" className="space-y-4 p-8">\n'
                '      <h1 className="text-3xl font-semibold text-[#171717]">Frontend incident board</h1>\n'
                "      {visibleIncidents.length === 0 ? (\n"
                '        <p className="text-sm text-[#5f6470]">No active incidents in the drill board.</p>\n'
                "      ) : (\n"
                '        <ul className="space-y-2 text-sm text-[#171717]">\n'
                "          {visibleIncidents.map((incident) => (\n"
                '            <li key={incident.id}>{incident.title}</li>\n'
                "          ))}\n"
                "        </ul>\n"
                "      )}\n"
                "    </main>\n"
                "  );\n"
                "}\n"
            ),
        },
    ),
    "frontend-failure-banner": DrillScenario(
        name="frontend-failure-banner",
        bug_class="frontend-failure-banner",
        difficulty="hard",
        error_summary="Frontend autonomous run panel hid the failure banner even though the latest run had failed",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/client-ui/src/components/frontend-drill/failure-banner.tsx", line 9, in FailureBanner\n'
            'AssertionError: expected failed autonomous run banner to stay visible'
        ),
        request_path="/frontend-drill/failure-banner",
        response_status_code=503,
        challenge_tags=("client-ui", "component-logic", "conditional-rendering"),
        fixture_files={
            **_frontend_drill_support_files(
                contains_text=["Autonomous repair stopped: Browser verification timed out."],
            ),
            "client-ui/src/components/frontend-drill/failure-banner.tsx": (
                'type DrillRun = { status: "failed" | "succeeded"; lastError: string | null };\n\n'
                "export function FailureBanner({ run }: { run: DrillRun }) {\n"
                '  const shouldShowError = run.status === "succeeded" && Boolean(run.lastError);\n'
                "  if (!shouldShowError || !run.lastError) {\n"
                "    return null;\n"
                "  }\n\n"
                "  return (\n"
                '    <p className="rounded-xl border border-[rgba(255,106,61,0.2)] bg-[rgba(255,106,61,0.08)] px-3 py-2 text-sm text-[#9b3719]">\n'
                "      {run.lastError}\n"
                "    </p>\n"
                "  );\n"
                "}\n"
            ),
            "client-ui/src/app/frontend-drill/page.tsx": (
                'import { FailureBanner } from "@/components/frontend-drill/failure-banner";\n\n'
                "const run = {\n"
                '  status: "failed" as const,\n'
                '  lastError: "Autonomous repair stopped: Browser verification timed out.",\n'
                "};\n\n"
                "export default function FrontendDrillPage() {\n"
                "  return (\n"
                '    <main data-drill-root="frontend-drill" className="space-y-4 p-8">\n'
                '      <h1 className="text-3xl font-semibold text-[#171717]">Frontend autonomous drill</h1>\n'
                '      <p className="text-sm text-[#5f6470]">The latest run should surface its failure details to operators.</p>\n'
                "      <FailureBanner run={run} />\n"
                "    </main>\n"
                "  );\n"
                "}\n"
            ),
        },
    ),
    "frontend-env-mode-default": DrillScenario(
        name="frontend-env-mode-default",
        bug_class="frontend-env-mode-default",
        difficulty="hard",
        error_summary="Frontend drill mode badge used the wrong default label when no environment override was present",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/client-ui/src/app/frontend-drill/page.tsx", line 9, in FrontendDrillPage\n'
            'AssertionError: expected frontend drill mode to default to "monitoring"'
        ),
        request_path="/frontend-drill/env-mode",
        response_status_code=503,
        challenge_tags=("client-ui", "env-config", "default-behavior"),
        fixture_files={
            **_frontend_drill_support_files(
                contains_text=["Mode: monitoring"],
                not_contains_text=["Mode: stable"],
            ),
            "client-ui/src/lib/frontend-drill/config.ts": (
                "export function frontendDrillMode(): string {\n"
                '  return process.env.NEXT_PUBLIC_FRONTEND_DRILL_MODE ?? "stable";\n'
                "}\n"
            ),
            "client-ui/src/app/frontend-drill/page.tsx": (
                'import { frontendDrillMode } from "@/lib/frontend-drill/config";\n\n'
                "export default function FrontendDrillPage() {\n"
                "  return (\n"
                '    <main data-drill-root="frontend-drill" className="space-y-4 p-8">\n'
                '      <h1 className="text-3xl font-semibold text-[#171717]">Frontend environment drill</h1>\n'
                '      <p className="text-sm text-[#5f6470]">{`Mode: ${frontendDrillMode()}`}</p>\n'
                "    </main>\n"
                "  );\n"
                "}\n"
            ),
        },
    ),
    "frontend-misleading-cascade": DrillScenario(
        name="frontend-misleading-cascade",
        bug_class="frontend-misleading-cascade",
        difficulty="very-hard",
        error_summary="Frontend retry card still rendered the wrong copy after the first apparent fix",
        stacktrace=(
            "Traceback:\n"
            '  File "/workspace/repo/client-ui/src/app/frontend-drill/page.tsx", line 16, in FrontendDrillPage\n'
            'AssertionError: expected retry card to show "Retry again in 15 minutes" and "Follow-up required"'
        ),
        request_path="/frontend-drill/misleading-cascade",
        response_status_code=503,
        challenge_tags=("client-ui", "iterative-repair", "multiple-failures", "wrong-first-fix"),
        fixture_files={
            **_frontend_drill_support_files(
                contains_text=["Retry again in 15 minutes", "Follow-up required"],
                not_contains_text=["Retry again in 5 minutes", "Follow-up not required"],
            ),
            "client-ui/src/lib/frontend-drill/formatters.ts": (
                "export function formatRetryDelay(value: string): string {\n"
                '  return `Retry again in ${value.slice(1)} minutes`;\n'
                "}\n"
            ),
            "client-ui/src/lib/frontend-drill/summary.ts": (
                "export function buildFollowUpSummary(requiresFollowUp: boolean): string {\n"
                '  return requiresFollowUp ? "Follow-up not required" : "Follow-up required";\n'
                "}\n"
            ),
            "client-ui/src/app/frontend-drill/page.tsx": (
                'import { formatRetryDelay } from "@/lib/frontend-drill/formatters";\n'
                'import { buildFollowUpSummary } from "@/lib/frontend-drill/summary";\n\n'
                "const retryAfter = \"15\";\n"
                "const requiresFollowUp = true;\n\n"
                "export default function FrontendDrillPage() {\n"
                "  return (\n"
                '    <main data-drill-root="frontend-drill" className="space-y-4 p-8">\n'
                '      <h1 className="text-3xl font-semibold text-[#171717]">Frontend retry card</h1>\n'
                '      <p className="text-sm text-[#171717]">{formatRetryDelay(retryAfter)}</p>\n'
                '      <p className="text-sm text-[#5f6470]">{buildFollowUpSummary(requiresFollowUp)}</p>\n'
                "    </main>\n"
                "  );\n"
                "}\n"
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
                "difficulty": scenario.difficulty,
                "error_summary": scenario.error_summary,
                "request_path": scenario.request_path,
                "response_status_code": scenario.response_status_code,
                "challenge_tags": list(scenario.challenge_tags),
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
        "difficulty": scenario.difficulty,
        "challenge_tags": list(scenario.challenge_tags),
        "repository_root": repository_root,
        "run_id": run.get("id"),
        "status": run.get("status"),
        "phase": run.get("phase"),
        "total_steps": outcome.get("total_steps"),
        "recovery_attempts": outcome.get("recovery_attempts"),
        "stagnation_count": outcome.get("stagnation_count"),
        "fresh_verification_satisfied": outcome.get("fresh_verification_satisfied"),
        "failure_class": outcome.get("failure_class"),
        "last_error": run.get("last_error"),
        "require_browser_verification": (run.get("policy") or {}).get("require_browser_verification"),
        "latest_verification_kind": (run.get("latest_verification") or {}).get("kind"),
        "final_success": final_success,
    }


def _recommended_max_steps(scenario: DrillScenario) -> int:
    if "client-ui" in scenario.challenge_tags:
        return 20
    return 12


def _run_poll_reached_terminal_state(
    *,
    status: str | None,
    promotion_status: str | None,
    promote: bool,
) -> bool:
    if status in {"failed", "cancelled"}:
        return True
    if promote:
        return promotion_status == "proposed"
    return promotion_status in {"ready", "blocked", "proposed"}


def _load_all_benchmark_results(results_dir: str) -> list[dict[str, Any]]:
    directory = Path(results_dir).expanduser().resolve()
    if not directory.exists():
        raise RuntimeError(f"Benchmark results directory does not exist: {directory}")

    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda candidate: candidate.name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        scenario_id = payload.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            continue
        normalized = dict(payload)
        scenario = _DRILL_SCENARIOS.get(scenario_id)
        if scenario is not None:
            normalized.setdefault("bug_class", scenario.bug_class)
            normalized.setdefault("difficulty", scenario.difficulty)
            normalized.setdefault("challenge_tags", list(scenario.challenge_tags))
        normalized["source_file"] = str(path)
        results.append(normalized)
    return results


def _load_latest_benchmark_results(results_dir: str) -> list[dict[str, Any]]:
    all_results = _load_all_benchmark_results(results_dir)
    latest_by_scenario: dict[str, tuple[float, dict[str, Any], Path]] = {}
    for payload in all_results:
        path = Path(str(payload["source_file"]))
        scenario_id = str(payload["scenario_id"])
        stat = path.stat()
        current = latest_by_scenario.get(scenario_id)
        if current is None or stat.st_mtime > current[0]:
            latest_by_scenario[scenario_id] = (stat.st_mtime, payload, path)

    results: list[dict[str, Any]] = []
    for _mtime, payload, path in sorted(latest_by_scenario.values(), key=lambda item: item[2].name):
        normalized = dict(payload)
        scenario_id = str(normalized["scenario_id"])
        scenario = _DRILL_SCENARIOS.get(scenario_id)
        if scenario is not None:
            normalized.setdefault("bug_class", scenario.bug_class)
            normalized.setdefault("difficulty", scenario.difficulty)
            normalized.setdefault("challenge_tags", list(scenario.challenge_tags))
        normalized["source_file"] = str(path)
        results.append(normalized)
    return results


def _build_benchmark_summary(results_dir: str) -> dict[str, Any]:
    all_results = _load_all_benchmark_results(results_dir)
    latest_results = _load_latest_benchmark_results(results_dir)
    succeeded = [result for result in latest_results if bool(result.get("final_success"))]
    successful_attempts = [result for result in all_results if bool(result.get("final_success"))]
    by_difficulty: dict[str, dict[str, Any]] = {}
    by_tag: dict[str, dict[str, Any]] = {}
    attempts_by_difficulty: dict[str, dict[str, Any]] = {}
    attempts_by_tag: dict[str, dict[str, Any]] = {}
    attempts_by_scenario: dict[str, dict[str, Any]] = {}

    for result in latest_results:
        difficulty = str(result.get("difficulty") or "unknown")
        bucket = by_difficulty.setdefault(
            difficulty,
            {"difficulty": difficulty, "total": 0, "successful": 0, "average_steps": 0.0},
        )
        bucket["total"] += 1
        bucket["successful"] += int(bool(result.get("final_success")))
        total_steps = result.get("total_steps")
        if isinstance(total_steps, int):
            bucket["average_steps"] += float(total_steps)

        for tag in result.get("challenge_tags", []):
            label = str(tag)
            tag_bucket = by_tag.setdefault(label, {"tag": label, "total": 0, "successful": 0})
            tag_bucket["total"] += 1
            tag_bucket["successful"] += int(bool(result.get("final_success")))

    for result in all_results:
        difficulty = str(result.get("difficulty") or "unknown")
        bucket = attempts_by_difficulty.setdefault(
            difficulty,
            {"difficulty": difficulty, "total_attempts": 0, "successful_attempts": 0, "average_steps": 0.0},
        )
        bucket["total_attempts"] += 1
        bucket["successful_attempts"] += int(bool(result.get("final_success")))
        total_steps = result.get("total_steps")
        if isinstance(total_steps, int):
            bucket["average_steps"] += float(total_steps)

        scenario_id = str(result.get("scenario_id") or "unknown")
        scenario_bucket = attempts_by_scenario.setdefault(
            scenario_id,
            {"scenario_id": scenario_id, "total_attempts": 0, "successful_attempts": 0},
        )
        scenario_bucket["total_attempts"] += 1
        scenario_bucket["successful_attempts"] += int(bool(result.get("final_success")))

        for tag in result.get("challenge_tags", []):
            label = str(tag)
            tag_bucket = attempts_by_tag.setdefault(label, {"tag": label, "total_attempts": 0, "successful_attempts": 0})
            tag_bucket["total_attempts"] += 1
            tag_bucket["successful_attempts"] += int(bool(result.get("final_success")))

    for bucket in by_difficulty.values():
        total = int(bucket["total"])
        bucket["success_rate"] = (bucket["successful"] / total) if total else 0.0
        bucket["average_steps"] = (bucket["average_steps"] / total) if total else 0.0

    for bucket in by_tag.values():
        total = int(bucket["total"])
        bucket["success_rate"] = (bucket["successful"] / total) if total else 0.0

    for bucket in attempts_by_difficulty.values():
        total_attempts = int(bucket["total_attempts"])
        bucket["attempt_success_rate"] = (bucket["successful_attempts"] / total_attempts) if total_attempts else 0.0
        bucket["average_steps"] = (bucket["average_steps"] / total_attempts) if total_attempts else 0.0

    for bucket in attempts_by_tag.values():
        total_attempts = int(bucket["total_attempts"])
        bucket["attempt_success_rate"] = (bucket["successful_attempts"] / total_attempts) if total_attempts else 0.0

    flaky_scenarios = [
        {
            "scenario_id": scenario_id,
            "total_attempts": values["total_attempts"],
            "successful_attempts": values["successful_attempts"],
            "attempt_success_rate": (values["successful_attempts"] / values["total_attempts"])
            if values["total_attempts"]
            else 0.0,
        }
        for scenario_id, values in sorted(attempts_by_scenario.items())
        if 0 < values["successful_attempts"] < values["total_attempts"]
    ]

    return {
        "schema_version": 1,
        "generated_from": "staging_drill_summary",
        "results_directory": str(Path(results_dir).expanduser().resolve()),
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_count": len(latest_results),
        "successful_scenarios": len(succeeded),
        "success_rate": (len(succeeded) / len(latest_results)) if latest_results else 0.0,
        "attempt_count": len(all_results),
        "successful_attempts": len(successful_attempts),
        "attempt_success_rate": (len(successful_attempts) / len(all_results)) if all_results else 0.0,
        "by_difficulty": sorted(by_difficulty.values(), key=lambda item: str(item["difficulty"])),
        "by_challenge_tag": sorted(by_tag.values(), key=lambda item: str(item["tag"])),
        "attempts_by_difficulty": sorted(attempts_by_difficulty.values(), key=lambda item: str(item["difficulty"])),
        "attempts_by_challenge_tag": sorted(attempts_by_tag.values(), key=lambda item: str(item["tag"])),
        "flaky_scenarios": flaky_scenarios,
        "scenarios": latest_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a golden-path staging drill.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Backend API base URL.")
    parser.add_argument("--project-id", required=False, help="Project id used for telemetry and incident lookup.")
    parser.add_argument("--service", default="billing-api", help="Service name for the synthetic telemetry.")
    parser.add_argument("--environment", default="staging", help="Telemetry environment.")
    parser.add_argument("--repository-root", default=None, help="Repository root path for the autonomous run.")
    parser.add_argument(
        "--summarize-results-dir",
        default=None,
        help="Optional benchmark results directory to summarize instead of running a live drill.",
    )
    parser.add_argument("--summary-path", default=None, help="Optional path to write a benchmark summary JSON report.")
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

    if args.summarize_results_dir:
        summary = _build_benchmark_summary(args.summarize_results_dir)
        print(json.dumps(summary, indent=2))
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    if not args.project_id:
        raise RuntimeError("--project-id is required unless --summarize-results-dir is provided.")

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
        "max_steps": _recommended_max_steps(scenario),
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
    terminal_failure = False
    poll_completed = False
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
            terminal_failure = True
            poll_completed = True
            break
        if args.promote and promotion_status == "ready":
            latest_detail = _http_json(
                "POST",
                f"{args.api_url}/incidents/{incident_id}/autonomous-runs/{run_id}/promote",
            )
            promotion_status = latest_detail["run"].get("promotion_status")
        if _run_poll_reached_terminal_state(
            status=status,
            promotion_status=promotion_status,
            promote=args.promote,
        ):
            poll_completed = True
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
    if not poll_completed:
        raise RuntimeError(
            json.dumps(
                {
                    "error": "Timed out waiting for autonomous run completion.",
                    "final_run_detail": latest_detail,
                },
                indent=2,
            )
        )
    if terminal_failure:
        raise RuntimeError(json.dumps(latest_detail, indent=2))


if __name__ == "__main__":
    main()

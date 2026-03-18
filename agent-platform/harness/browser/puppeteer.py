from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.browser.base import BrowserAutomationBackend
from harness.schemas.browser import (
    BrowserAction,
    BrowserActionResult,
    BrowserAssertTextRequest,
    BrowserCaptureConsoleLogsRequest,
    BrowserCaptureNetworkSummaryRequest,
    BrowserClickRequest,
    BrowserCloseRequest,
    BrowserCurrentPageStateRequest,
    BrowserGetUrlRequest,
    BrowserOpenRequest,
    BrowserProvider,
    BrowserScreenshotRequest,
    BrowserSnapshotDomRequest,
    BrowserTypeRequest,
    BrowserWaitForRequest,
)


class PuppeteerBrowserBackend(BrowserAutomationBackend):
    def __init__(
        self,
        *,
        node_binary: str = "node",
        worker_path: str | None = None,
    ) -> None:
        self._node_binary = node_binary
        self._worker_path = worker_path or str(Path(__file__).with_name("puppeteer_worker.mjs"))
        self._process: subprocess.Popen[str] | None = None

    def open(self, request: BrowserOpenRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.OPEN, request.model_dump(mode="json"))

    def click(self, request: BrowserClickRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.CLICK, request.model_dump(mode="json"))

    def type(self, request: BrowserTypeRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.TYPE, request.model_dump(mode="json"))

    def wait_for(self, request: BrowserWaitForRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.WAIT_FOR, request.model_dump(mode="json"))

    def snapshot_dom(self, request: BrowserSnapshotDomRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.SNAPSHOT_DOM, request.model_dump(mode="json"))

    def dom_snapshot(self, request: BrowserSnapshotDomRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.DOM_SNAPSHOT, request.model_dump(mode="json"))

    def screenshot(self, request: BrowserScreenshotRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.SCREENSHOT, request.model_dump(mode="json"))

    def take_screenshot(self, request: BrowserScreenshotRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.TAKE_SCREENSHOT, request.model_dump(mode="json"))

    def get_url(self, request: BrowserGetUrlRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.GET_URL, request.model_dump(mode="json"))

    def assert_text(self, request: BrowserAssertTextRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.ASSERT_TEXT, request.model_dump(mode="json"))

    def capture_console_logs(self, request: BrowserCaptureConsoleLogsRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.CAPTURE_CONSOLE_LOGS, request.model_dump(mode="json"))

    def capture_network_summary(
        self,
        request: BrowserCaptureNetworkSummaryRequest,
    ) -> BrowserActionResult:
        return self._invoke(BrowserAction.CAPTURE_NETWORK_SUMMARY, request.model_dump(mode="json"))

    def current_page_state(self, request: BrowserCurrentPageStateRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.CURRENT_PAGE_STATE, request.model_dump(mode="json"))

    def close_session(self, request: BrowserCloseRequest) -> BrowserActionResult:
        return self._invoke(BrowserAction.CLOSE, request.model_dump(mode="json"))

    def shutdown(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._send_command({"action": "shutdown"})
            self._process.wait(timeout=10)
        self._process = None

    def _invoke(self, action: BrowserAction, payload: dict[str, object]) -> BrowserActionResult:
        response = self._send_command(
            {
                "action": action.value,
                "payload": payload,
            }
        )
        if response.get("action") == "unknown":
            response["action"] = action.value
        response.setdefault("provider", BrowserProvider.PUPPETEER.value)
        response.setdefault("action", action.value)
        response.setdefault("message", action.value)
        return BrowserActionResult.model_validate(response)

    def _send_command(self, command: dict[str, object]) -> dict[str, object]:
        process = self._ensure_process()
        assert process.stdin is not None
        assert process.stdout is not None

        process.stdin.write(json.dumps(command) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr_output = ""
            if process.stderr is not None:
                stderr_output = process.stderr.read().strip()
            raise RuntimeError(f"Puppeteer worker terminated unexpectedly. {stderr_output}".strip())
        return json.loads(line)

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process

        self._process = subprocess.Popen(
            [self._node_binary, self._worker_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self._process

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass

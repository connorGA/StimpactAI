from __future__ import annotations

from typing import Protocol

from harness.schemas.browser import (
    BrowserActionResult,
    BrowserAssertTextRequest,
    BrowserCaptureConsoleLogsRequest,
    BrowserCaptureNetworkSummaryRequest,
    BrowserClickRequest,
    BrowserCloseRequest,
    BrowserCurrentPageStateRequest,
    BrowserGetUrlRequest,
    BrowserOpenRequest,
    BrowserScreenshotRequest,
    BrowserSnapshotDomRequest,
    BrowserTypeRequest,
    BrowserWaitForRequest,
)


class BrowserAutomationBackend(Protocol):
    def open(self, request: BrowserOpenRequest) -> BrowserActionResult: ...

    def click(self, request: BrowserClickRequest) -> BrowserActionResult: ...

    def type(self, request: BrowserTypeRequest) -> BrowserActionResult: ...

    def wait_for(self, request: BrowserWaitForRequest) -> BrowserActionResult: ...

    def snapshot_dom(self, request: BrowserSnapshotDomRequest) -> BrowserActionResult: ...

    def dom_snapshot(self, request: BrowserSnapshotDomRequest) -> BrowserActionResult: ...

    def screenshot(self, request: BrowserScreenshotRequest) -> BrowserActionResult: ...

    def take_screenshot(self, request: BrowserScreenshotRequest) -> BrowserActionResult: ...

    def get_url(self, request: BrowserGetUrlRequest) -> BrowserActionResult: ...

    def assert_text(self, request: BrowserAssertTextRequest) -> BrowserActionResult: ...

    def capture_console_logs(self, request: BrowserCaptureConsoleLogsRequest) -> BrowserActionResult: ...

    def capture_network_summary(
        self, request: BrowserCaptureNetworkSummaryRequest
    ) -> BrowserActionResult: ...

    def current_page_state(self, request: BrowserCurrentPageStateRequest) -> BrowserActionResult: ...

    def close_session(self, request: BrowserCloseRequest) -> BrowserActionResult: ...

    def shutdown(self) -> None: ...

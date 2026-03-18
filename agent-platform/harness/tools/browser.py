from __future__ import annotations

from uuid import uuid4

from harness.browser.base import BrowserAutomationBackend
from harness.browser.puppeteer import PuppeteerBrowserBackend
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
    BrowserProvider,
    BrowserScreenshotRequest,
    BrowserSnapshotDomRequest,
    BrowserTypeRequest,
    BrowserWaitForRequest,
)


class BrowserToolSessionManager:
    def __init__(
        self,
        *,
        provider: BrowserProvider = BrowserProvider.PUPPETEER,
        backend: BrowserAutomationBackend | None = None,
    ) -> None:
        self._provider = provider
        self._backend = backend or self._build_backend(provider)

    def browser_open(
        self,
        *,
        url: str,
        session_id: str | None = None,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        request = BrowserOpenRequest(
            session_id=session_id or self._new_session_id(),
            url=url,
            timeout_ms=timeout_ms,
        )
        return self._backend.open(request)

    def browser_click(
        self,
        *,
        session_id: str,
        selector: str,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.click(
            BrowserClickRequest(session_id=session_id, selector=selector, timeout_ms=timeout_ms)
        )

    def browser_type(
        self,
        *,
        session_id: str,
        selector: str,
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.type(
            BrowserTypeRequest(
                session_id=session_id,
                selector=selector,
                text=text,
                clear_first=clear_first,
                press_enter=press_enter,
                timeout_ms=timeout_ms,
            )
        )

    def browser_wait_for(
        self,
        *,
        session_id: str,
        selector: str | None = None,
        text: str | None = None,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.wait_for(
            BrowserWaitForRequest(
                session_id=session_id,
                selector=selector,
                text=text,
                timeout_ms=timeout_ms,
            )
        )

    def browser_snapshot_dom(
        self,
        *,
        session_id: str,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.snapshot_dom(
            BrowserSnapshotDomRequest(session_id=session_id, timeout_ms=timeout_ms)
        )

    def dom_snapshot(
        self,
        *,
        session_id: str,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.dom_snapshot(
            BrowserSnapshotDomRequest(session_id=session_id, timeout_ms=timeout_ms)
        )

    def browser_screenshot(
        self,
        *,
        session_id: str,
        output_path: str,
        full_page: bool = True,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.screenshot(
            BrowserScreenshotRequest(
                session_id=session_id,
                output_path=output_path,
                full_page=full_page,
                timeout_ms=timeout_ms,
            )
        )

    def take_screenshot(
        self,
        *,
        session_id: str,
        output_path: str,
        full_page: bool = True,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.take_screenshot(
            BrowserScreenshotRequest(
                session_id=session_id,
                output_path=output_path,
                full_page=full_page,
                timeout_ms=timeout_ms,
            )
        )

    def browser_get_url(
        self,
        *,
        session_id: str,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.get_url(
            BrowserGetUrlRequest(session_id=session_id, timeout_ms=timeout_ms)
        )

    def browser_assert_text(
        self,
        *,
        session_id: str,
        text: str,
        selector: str | None = None,
        exact: bool = False,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.assert_text(
            BrowserAssertTextRequest(
                session_id=session_id,
                text=text,
                selector=selector,
                exact=exact,
                timeout_ms=timeout_ms,
            )
        )

    def capture_console_logs(
        self,
        *,
        session_id: str,
        limit: int = 25,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.capture_console_logs(
            BrowserCaptureConsoleLogsRequest(
                session_id=session_id,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        )

    def capture_network_summary(
        self,
        *,
        session_id: str,
        limit: int = 25,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.capture_network_summary(
            BrowserCaptureNetworkSummaryRequest(
                session_id=session_id,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        )

    def current_page_state(
        self,
        *,
        session_id: str,
        include_dom: bool = False,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.current_page_state(
            BrowserCurrentPageStateRequest(
                session_id=session_id,
                include_dom=include_dom,
                timeout_ms=timeout_ms,
            )
        )

    def browser_close(
        self,
        *,
        session_id: str,
        timeout_ms: int = 5_000,
    ) -> BrowserActionResult:
        return self._backend.close_session(
            BrowserCloseRequest(session_id=session_id, timeout_ms=timeout_ms)
        )

    def shutdown(self) -> None:
        self._backend.shutdown()

    def _build_backend(self, provider: BrowserProvider) -> BrowserAutomationBackend:
        if provider is BrowserProvider.PUPPETEER:
            return PuppeteerBrowserBackend()
        raise ValueError(f"Unsupported browser provider: {provider}")

    def _new_session_id(self) -> str:
        return f"browser-{uuid4()}"


_DEFAULT_MANAGER = BrowserToolSessionManager()


def browser_open(*, url: str, session_id: str | None = None, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_open(url=url, session_id=session_id, timeout_ms=timeout_ms)


def browser_click(*, session_id: str, selector: str, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_click(session_id=session_id, selector=selector, timeout_ms=timeout_ms)


def browser_type(
    *,
    session_id: str,
    selector: str,
    text: str,
    clear_first: bool = True,
    press_enter: bool = False,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_type(
        session_id=session_id,
        selector=selector,
        text=text,
        clear_first=clear_first,
        press_enter=press_enter,
        timeout_ms=timeout_ms,
    )


def browser_wait_for(
    *,
    session_id: str,
    selector: str | None = None,
    text: str | None = None,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_wait_for(
        session_id=session_id,
        selector=selector,
        text=text,
        timeout_ms=timeout_ms,
    )


def browser_snapshot_dom(*, session_id: str, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_snapshot_dom(session_id=session_id, timeout_ms=timeout_ms)


def dom_snapshot(*, session_id: str, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.dom_snapshot(session_id=session_id, timeout_ms=timeout_ms)


def browser_screenshot(
    *,
    session_id: str,
    output_path: str,
    full_page: bool = True,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_screenshot(
        session_id=session_id,
        output_path=output_path,
        full_page=full_page,
        timeout_ms=timeout_ms,
    )


def take_screenshot(
    *,
    session_id: str,
    output_path: str,
    full_page: bool = True,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.take_screenshot(
        session_id=session_id,
        output_path=output_path,
        full_page=full_page,
        timeout_ms=timeout_ms,
    )


def browser_get_url(*, session_id: str, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_get_url(session_id=session_id, timeout_ms=timeout_ms)


def browser_assert_text(
    *,
    session_id: str,
    text: str,
    selector: str | None = None,
    exact: bool = False,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_assert_text(
        session_id=session_id,
        text=text,
        selector=selector,
        exact=exact,
        timeout_ms=timeout_ms,
    )


def capture_console_logs(
    *,
    session_id: str,
    limit: int = 25,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.capture_console_logs(
        session_id=session_id,
        limit=limit,
        timeout_ms=timeout_ms,
    )


def capture_network_summary(
    *,
    session_id: str,
    limit: int = 25,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.capture_network_summary(
        session_id=session_id,
        limit=limit,
        timeout_ms=timeout_ms,
    )


def current_page_state(
    *,
    session_id: str,
    include_dom: bool = False,
    timeout_ms: int = 5_000,
) -> BrowserActionResult:
    return _DEFAULT_MANAGER.current_page_state(
        session_id=session_id,
        include_dom=include_dom,
        timeout_ms=timeout_ms,
    )


def browser_close(*, session_id: str, timeout_ms: int = 5_000) -> BrowserActionResult:
    return _DEFAULT_MANAGER.browser_close(session_id=session_id, timeout_ms=timeout_ms)

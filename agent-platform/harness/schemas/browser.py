from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BrowserProvider(StrEnum):
    PUPPETEER = "puppeteer"


class BrowserWaitUntil(StrEnum):
    LOAD = "load"
    DOMCONTENTLOADED = "domcontentloaded"
    NETWORKIDLE0 = "networkidle0"
    NETWORKIDLE2 = "networkidle2"


class BrowserAction(StrEnum):
    OPEN = "browser_open"
    CLICK = "browser_click"
    TYPE = "browser_type"
    WAIT_FOR = "browser_wait_for"
    SNAPSHOT_DOM = "browser_snapshot_dom"
    SCREENSHOT = "browser_screenshot"
    GET_URL = "browser_get_url"
    ASSERT_TEXT = "browser_assert_text"
    DOM_SNAPSHOT = "dom_snapshot"
    TAKE_SCREENSHOT = "take_screenshot"
    CAPTURE_CONSOLE_LOGS = "capture_console_logs"
    CAPTURE_NETWORK_SUMMARY = "capture_network_summary"
    CURRENT_PAGE_STATE = "current_page_state"
    CLOSE = "browser_close"


class BrowserToolRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    timeout_ms: int = Field(default=5_000, ge=100, le=120_000)


class BrowserOpenRequest(BrowserToolRequestBase):
    url: str = Field(min_length=1, max_length=4_096)
    headless: bool = True
    wait_until: BrowserWaitUntil = BrowserWaitUntil.DOMCONTENTLOADED
    width: int = Field(default=1280, ge=320, le=4000)
    height: int = Field(default=800, ge=240, le=4000)


class BrowserClickRequest(BrowserToolRequestBase):
    selector: str = Field(min_length=1, max_length=512)


class BrowserTypeRequest(BrowserToolRequestBase):
    selector: str = Field(min_length=1, max_length=512)
    text: str = Field(max_length=20_000)
    clear_first: bool = True
    press_enter: bool = False


class BrowserWaitForRequest(BrowserToolRequestBase):
    selector: str | None = Field(default=None, max_length=512)
    text: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_target(self) -> "BrowserWaitForRequest":
        if not self.selector and not self.text:
            raise ValueError("Either selector or text must be provided.")
        return self


class BrowserSnapshotDomRequest(BrowserToolRequestBase):
    pass


class BrowserScreenshotRequest(BrowserToolRequestBase):
    output_path: str = Field(min_length=1, max_length=4_096)
    full_page: bool = True


class BrowserGetUrlRequest(BrowserToolRequestBase):
    pass


class BrowserAssertTextRequest(BrowserToolRequestBase):
    text: str = Field(min_length=1, max_length=2_000)
    selector: str | None = Field(default=None, max_length=512)
    exact: bool = False


class BrowserCloseRequest(BrowserToolRequestBase):
    pass


class BrowserCaptureConsoleLogsRequest(BrowserToolRequestBase):
    limit: int = Field(default=25, ge=1, le=200)


class BrowserCaptureNetworkSummaryRequest(BrowserToolRequestBase):
    limit: int = Field(default=25, ge=1, le=200)


class BrowserCurrentPageStateRequest(BrowserToolRequestBase):
    include_dom: bool = False


class BrowserConsoleLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4_000)
    url: str | None = Field(default=None, max_length=4_096)
    line_number: int | None = Field(default=None, ge=0)


class BrowserJavaScriptException(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4_000)
    stack: str | None = Field(default=None, max_length=16_000)


class BrowserNetworkRequestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4_096)
    method: str = Field(min_length=1, max_length=32)
    resource_type: str = Field(min_length=1, max_length=64)
    status: int | None = Field(default=None, ge=0, le=999)
    ok: bool | None = None
    failure_text: str | None = Field(default=None, max_length=1_000)


class BrowserNetworkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_requests: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    total_error_responses: int = Field(ge=0)
    recent_requests: list[BrowserNetworkRequestEntry] = Field(default_factory=list)


class BrowserPageState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_url: str | None = Field(default=None, max_length=4_096)
    title: str | None = Field(default=None, max_length=1_000)
    ready_state: str | None = Field(default=None, max_length=64)
    console_error_count: int = Field(default=0, ge=0)
    js_exception_count: int = Field(default=0, ge=0)
    failed_request_count: int = Field(default=0, ge=0)
    dom_length: int | None = Field(default=None, ge=0)


class BrowserActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    provider: BrowserProvider
    action: BrowserAction
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2_000)
    current_url: str | None = Field(default=None, max_length=4_096)
    dom_snapshot: str | None = None
    screenshot_path: str | None = Field(default=None, max_length=4_096)
    matched_text: str | None = Field(default=None, max_length=2_000)
    console_logs: list[BrowserConsoleLogEntry] = Field(default_factory=list)
    js_exceptions: list[BrowserJavaScriptException] = Field(default_factory=list)
    network_summary: BrowserNetworkSummary | None = None
    page_state: BrowserPageState | None = None
    elapsed_ms: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=4_000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized

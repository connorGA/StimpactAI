from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from harness.schemas.browser import BrowserAction
from harness.tools.browser import BrowserToolSessionManager


def test_browser_inspection_tools_capture_console_network_and_page_state(tmp_path: Path) -> None:
    page_root = tmp_path / "site"
    page_root.mkdir()
    (page_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Inspection Demo</title>
  </head>
  <body>
    <div id="status">Booting</div>
    <script>
      console.error("console exploded");
      fetch("http://127.0.0.1:9/unreachable.json").catch(() => {
        document.getElementById("status").dataset.network = "failed";
      });
      setTimeout(() => {
        throw new Error("kaboom from browser");
      }, 10);
      setTimeout(() => {
        document.getElementById("status").innerText = "Diagnostics complete";
      }, 50);
    </script>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    manager = BrowserToolSessionManager()
    with serve_directory(page_root) as base_url:
        opened = manager.browser_open(url=f"{base_url}/index.html", timeout_ms=10_000)
        assert opened.ok is True
        session_id = opened.session_id

        waited = manager.browser_wait_for(
            session_id=session_id,
            text="Diagnostics complete",
            selector="#status",
            timeout_ms=10_000,
        )
        assert waited.ok is True

        console_result = manager.capture_console_logs(session_id=session_id, limit=20)
        assert console_result.ok is True
        assert any("console exploded" in entry.text for entry in console_result.console_logs)
        assert any(exception.message == "kaboom from browser" for exception in console_result.js_exceptions)

        network_result = manager.capture_network_summary(session_id=session_id, limit=20)
        assert network_result.ok is True
        assert network_result.network_summary is not None
        assert network_result.network_summary.total_requests >= 1
        assert network_result.network_summary.total_failures >= 1

        page_state = manager.current_page_state(session_id=session_id, include_dom=True)
        assert page_state.ok is True
        assert page_state.action is BrowserAction.CURRENT_PAGE_STATE
        assert page_state.page_state is not None
        assert page_state.page_state.title == "Inspection Demo"
        assert page_state.page_state.ready_state == "complete"
        assert page_state.page_state.console_error_count >= 1
        assert page_state.page_state.js_exception_count >= 1
        assert page_state.page_state.failed_request_count >= 1
        assert page_state.page_state.dom_length is not None

        dom_result = manager.dom_snapshot(session_id=session_id)
        assert dom_result.ok is True
        assert dom_result.action is BrowserAction.DOM_SNAPSHOT
        assert dom_result.dom_snapshot is not None
        assert "Diagnostics complete" in dom_result.dom_snapshot

        screenshot_path = tmp_path / "artifacts" / "inspection.png"
        screenshot_result = manager.take_screenshot(
            session_id=session_id,
            output_path=str(screenshot_path),
        )
        assert screenshot_result.ok is True
        assert screenshot_result.action is BrowserAction.TAKE_SCREENSHOT
        assert screenshot_path.exists()

        closed = manager.browser_close(session_id=session_id)
        assert closed.ok is True

    manager.shutdown()


@contextmanager
def serve_directory(root: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)

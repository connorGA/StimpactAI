from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from harness.tools.browser import BrowserToolSessionManager


def test_browser_tool_manager_drives_local_page_with_puppeteer(tmp_path: Path) -> None:
    page_root = tmp_path / "site"
    page_root.mkdir()
    (page_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Harness Browser Test</title>
  </head>
  <body>
    <h1>Automation Demo</h1>
    <label for="name">Name</label>
    <input id="name" />
    <button id="apply" type="button">Apply</button>
    <div id="result">Waiting</div>
    <script>
      document.getElementById("apply").addEventListener("click", () => {
        const value = document.getElementById("name").value;
        document.getElementById("result").innerText = `Hello ${value}`;
        window.location.hash = "done";
      });
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
        assert_text_result = manager.browser_assert_text(session_id=session_id, text="Automation Demo")
        assert assert_text_result.ok is True

        typed = manager.browser_type(session_id=session_id, selector="#name", text="Connor")
        assert typed.ok is True

        clicked = manager.browser_click(session_id=session_id, selector="#apply")
        assert clicked.ok is True

        waited = manager.browser_wait_for(session_id=session_id, text="Hello Connor", selector="#result")
        assert waited.ok is True

        url_result = manager.browser_get_url(session_id=session_id)
        assert url_result.ok is True
        assert url_result.current_url is not None
        assert url_result.current_url.endswith("#done")

        dom_result = manager.browser_snapshot_dom(session_id=session_id)
        assert dom_result.ok is True
        assert dom_result.dom_snapshot is not None
        assert "Hello Connor" in dom_result.dom_snapshot

        screenshot_path = tmp_path / "artifacts" / "browser.png"
        screenshot = manager.browser_screenshot(
            session_id=session_id,
            output_path=str(screenshot_path),
        )
        assert screenshot.ok is True
        assert screenshot_path.exists()

        missing_text = manager.browser_assert_text(session_id=session_id, text="This should not exist")
        assert missing_text.ok is False
        assert missing_text.error is not None

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

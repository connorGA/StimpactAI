from __future__ import annotations

from pathlib import Path

from harness.schemas.viewer import FileViewAtLineRequest, FileViewRequest
from harness.tools.file_viewer import FileViewerSessionManager


def _write_numbered_file(path: Path, *, line_count: int) -> None:
    path.write_text(
        "\n".join(f"line {index}" for index in range(1, line_count + 1)),
        encoding="utf-8",
    )


def test_open_file_shows_first_page_with_line_numbers(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    _write_numbered_file(target, line_count=150)
    manager = FileViewerSessionManager()

    response = manager.open_file(FileViewRequest(file_path=str(target)))

    assert response.ok is True
    assert response.current_start_line == 1
    assert response.current_end_line == 100
    assert response.total_line_count == 150
    assert response.lines[0] == "1|line 1"
    assert response.lines[-1] == "100|line 100"


def test_view_next_and_prev_maintain_state_across_calls(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    _write_numbered_file(target, line_count=250)
    manager = FileViewerSessionManager()

    manager.open_file(FileViewRequest(file_path=str(target)))
    next_response = manager.view_next(FileViewRequest(file_path=str(target)))
    prev_response = manager.view_prev(FileViewRequest(file_path=str(target)))

    assert next_response.current_start_line == 101
    assert next_response.current_end_line == 200
    assert next_response.lines[0] == "101|line 101"
    assert prev_response.current_start_line == 1
    assert prev_response.current_end_line == 100


def test_view_at_line_jumps_to_requested_line_window(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    _write_numbered_file(target, line_count=250)
    manager = FileViewerSessionManager()

    response = manager.view_at_line(FileViewAtLineRequest(file_path=str(target), line=125))

    assert response.ok is True
    assert response.current_start_line == 125
    assert response.current_end_line == 224
    assert response.lines[0] == "125|line 125"


def test_view_centered_centers_line_when_possible(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    _write_numbered_file(target, line_count=250)
    manager = FileViewerSessionManager()

    response = manager.view_centered(FileViewAtLineRequest(file_path=str(target), line=150))

    assert response.ok is True
    assert response.current_start_line == 100
    assert response.current_end_line == 199
    assert "150|line 150" in response.lines


def test_viewer_clamps_to_file_boundaries(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    _write_numbered_file(target, line_count=120)
    manager = FileViewerSessionManager()

    response = manager.view_at_line(FileViewAtLineRequest(file_path=str(target), line=119))

    assert response.ok is True
    assert response.current_start_line == 21
    assert response.current_end_line == 120
    assert response.lines[-1] == "120|line 120"


def test_invalid_file_returns_structured_error() -> None:
    manager = FileViewerSessionManager()

    response = manager.open_file(FileViewRequest(file_path="/tmp/missing-viewer-file.txt"))

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "invalid_file"

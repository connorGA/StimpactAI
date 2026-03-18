from __future__ import annotations

from pathlib import Path

from harness.schemas.search import FindFileRequest, SearchDirRequest, SearchFileRequest
from harness.tools.search_tools import find_file, search_dir, search_file


def test_find_file_returns_capped_results_when_within_limit(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "src" / "app_test.py").write_text("print('test')\n", encoding="utf-8")

    response = find_file(
        FindFileRequest(
            root_path=str(tmp_path),
            query="app",
        )
    )

    assert response.ok is True
    assert response.too_many_results is False
    assert response.result_count == 2
    assert [item.path for item in response.results] == ["src/app.py", "src/app_test.py"]


def test_find_file_returns_refinement_response_when_results_exceed_limit(tmp_path: Path) -> None:
    for index in range(55):
        (tmp_path / f"match_{index}.py").write_text("print('hello')\n", encoding="utf-8")

    response = find_file(
        FindFileRequest(
            root_path=str(tmp_path),
            query="match",
        )
    )

    assert response.ok is True
    assert response.too_many_results is True
    assert response.result_count == 55
    assert response.results == []
    assert response.refinement_guidance is not None


def test_search_file_returns_no_results_when_query_missing(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    response = search_file(
        SearchFileRequest(
            file_path=str(target),
            query="missing",
        )
    )

    assert response.ok is True
    assert response.too_many_results is False
    assert response.result_count == 0
    assert response.results == []


def test_search_file_returns_invalid_path_response() -> None:
    response = search_file(
        SearchFileRequest(
            file_path="/tmp/does-not-exist.py",
            query="needle",
        )
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "invalid_path"


def test_search_dir_returns_structured_text_matches(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.py").write_text("needle here\n", encoding="utf-8")
    (tmp_path / "src" / "two.py").write_text("another needle here\n", encoding="utf-8")

    response = search_dir(
        SearchDirRequest(
            root_path=str(tmp_path / "src"),
            query="needle",
        )
    )

    assert response.ok is True
    assert response.too_many_results is False
    assert response.result_count == 2
    assert response.results[0].path == "one.py"
    assert response.results[0].line_number == 1
    assert response.results[1].path == "two.py"


def test_search_dir_returns_refinement_response_when_results_exceed_limit(tmp_path: Path) -> None:
    for index in range(51):
        (tmp_path / f"file_{index}.txt").write_text("needle\n", encoding="utf-8")

    response = search_dir(
        SearchDirRequest(
            root_path=str(tmp_path),
            query="needle",
        )
    )

    assert response.ok is True
    assert response.too_many_results is True
    assert response.result_count == 51
    assert response.results == []
    assert response.refinement_guidance is not None

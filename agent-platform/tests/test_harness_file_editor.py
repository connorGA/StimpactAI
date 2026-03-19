from __future__ import annotations

from pathlib import Path

from harness.schemas.editing import EditFileRequest
from harness.tools.file_editor import GuardedFileEditor


def test_guarded_editor_persists_successful_python_edit(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest(
            file_path=str(target),
            start_line=1,
            end_line=1,
            replacement_text="VALUE = 'new'",
        )
    )

    assert response.ok is True
    assert response.validation is not None
    assert response.validation.ok is True
    assert "Replaced lines 1-1" in (response.changed_region_summary or "")
    assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"


def test_guarded_editor_rejects_syntax_breaking_python_edit_without_persisting(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    original = "VALUE = 'old'\n"
    target.write_text(original, encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest(
            file_path=str(target),
            start_line=1,
            end_line=1,
            replacement_text="if True print('broken')",
        )
    )

    assert response.ok is False
    assert response.validation is not None
    assert response.validation.ok is False
    assert response.validation_failure is not None
    assert response.original_code == "VALUE = 'old'"
    assert target.read_text(encoding="utf-8") == original


def test_guarded_editor_rejects_out_of_range_edits(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest(
            file_path=str(target),
            start_line=2,
            end_line=2,
            replacement_text="VALUE = 'new'",
        )
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "line_range_out_of_bounds"


def test_guarded_editor_rejects_unsupported_file_type(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old text\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest(
            file_path=str(target),
            start_line=1,
            end_line=1,
            replacement_text="new text",
        )
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "unsupported_file_type"


def test_edit_request_accepts_legacy_string_replacement_arguments(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest.model_validate(
            {
                "file_path": str(target),
                "old_string": "VALUE = 'old'\n",
                "new_string": "VALUE = 'new'\n",
            }
        )
    )

    assert response.ok is True
    assert response.start_line == 1
    assert response.end_line == 1
    assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"


def test_edit_request_accepts_top_level_old_text_and_new_text_arguments(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest.model_validate(
            {
                "file_path": str(target),
                "old_text": "VALUE = 'old'\n",
                "new_text": "VALUE = 'newer'\n",
            }
        )
    )

    assert response.ok is True
    assert response.start_line == 1
    assert response.end_line == 1
    assert target.read_text(encoding="utf-8") == "VALUE = 'newer'\n"


def test_edit_request_accepts_whole_file_replacement_arguments(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest.model_validate(
            {
                "file_path": str(target),
                "new_content": "VALUE = 'replaced'\n",
            }
        )
    )

    assert response.ok is True
    assert response.start_line == 1
    assert response.end_line == 1
    assert target.read_text(encoding="utf-8") == "VALUE = 'replaced'\n"


def test_edit_request_accepts_single_edit_batch_arguments(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest.model_validate(
            {
                "file_path": str(target),
                "edits": [
                    {
                        "old_text": "VALUE = 'old'\n",
                        "new_text": "VALUE = 'batched'\n",
                    }
                ],
            }
        )
    )

    assert response.ok is True
    assert response.start_line == 1
    assert response.end_line == 1
    assert target.read_text(encoding="utf-8") == "VALUE = 'batched'\n"


def test_guarded_editor_validates_javascript_edits(tmp_path: Path) -> None:
    target = tmp_path / "script.js"
    target.write_text("const value = 1;\n", encoding="utf-8")
    editor = GuardedFileEditor()

    response = editor.edit_file(
        EditFileRequest(
            file_path=str(target),
            start_line=1,
            end_line=1,
            replacement_text="const value = 2;",
        )
    )

    assert response.ok is True
    assert response.validation is not None
    assert response.validation.ok is True
    assert target.read_text(encoding="utf-8") == "const value = 2;\n"

from __future__ import annotations

import tempfile
from pathlib import Path

from harness.schemas.editing import (
    EditError,
    EditFileRequest,
    EditFileResponse,
    ValidationResult,
    ValidationFailure,
)
from harness.validation.languages import get_validator_for_path


class GuardedFileEditor:
    def edit_file(self, request: EditFileRequest) -> EditFileResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_target_file(path)
        if validation_error is not None:
            return self._error_response(request, validation_error)

        original_text = path.read_text(encoding="utf-8")
        original_lines = original_text.splitlines()
        if request.end_line > max(1, len(original_lines)):
            return self._error_response(
                request,
                EditError(
                    code="line_range_out_of_bounds",
                    message=(
                        f"Requested edit range {request.start_line}-{request.end_line} "
                        f"exceeds file length {len(original_lines)}."
                    ),
                ),
            )

        validator = get_validator_for_path(path)
        if validator is None:
            return self._error_response(
                request,
                EditError(
                    code="unsupported_file_type",
                    message=f"Unsupported file type for guarded editing: {path.suffix or '<none>'}",
                ),
            )

        original_code = self._slice_original_code(original_lines, request.start_line, request.end_line)
        updated_text = self._build_updated_text(original_text, request)
        validation_result = self._validate_modified_text(path, updated_text, validator)
        if not validation_result.ok:
            return EditFileResponse(
                ok=False,
                file_path=str(path),
                start_line=request.start_line,
                end_line=request.end_line,
                changed_region_summary=None,
                original_code=original_code,
                replacement_text=request.replacement_text,
                validation=validation_result,
                validation_failure=ValidationFailure(
                    message=validation_result.message or "Validation failed.",
                    output=validation_result.output,
                ),
                error=None,
            )

        self._persist_atomic(path, updated_text)
        replacement_line_count = len(request.replacement_text.splitlines()) or 1
        return EditFileResponse(
            ok=True,
            file_path=str(path),
            start_line=request.start_line,
            end_line=request.end_line,
            changed_region_summary=(
                f"Replaced lines {request.start_line}-{request.end_line} "
                f"with {replacement_line_count} line(s)."
            ),
            original_code=original_code,
            replacement_text=request.replacement_text,
            validation=validation_result,
            validation_failure=None,
            error=None,
        )

    def _validate_target_file(self, path: Path) -> EditError | None:
        if not path.exists():
            return EditError(code="invalid_file", message=f"File does not exist: {path}")
        if not path.is_file():
            return EditError(code="invalid_file", message=f"Path is not a file: {path}")
        return None

    def _error_response(self, request: EditFileRequest, error: EditError) -> EditFileResponse:
        return EditFileResponse(
            ok=False,
            file_path=request.file_path,
            start_line=request.start_line,
            end_line=request.end_line,
            changed_region_summary=None,
            original_code="",
            replacement_text=request.replacement_text,
            validation=None,
            validation_failure=None,
            error=error,
        )

    def _slice_original_code(self, original_lines: list[str], start_line: int, end_line: int) -> str:
        return "\n".join(original_lines[start_line - 1 : end_line])

    def _build_updated_text(self, original_text: str, request: EditFileRequest) -> str:
        newline = "\r\n" if "\r\n" in original_text else "\n"
        had_trailing_newline = original_text.endswith(("\n", "\r"))
        original_lines = original_text.splitlines()
        replacement_lines = request.replacement_text.splitlines()
        updated_lines = (
            original_lines[: request.start_line - 1]
            + replacement_lines
            + original_lines[request.end_line :]
        )
        updated_text = newline.join(updated_lines)
        if had_trailing_newline and updated_lines:
            updated_text += newline
        return updated_text

    def _validate_modified_text(self, path: Path, updated_text: str, validator) -> ValidationResult:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=path.suffix,
            delete=False,
            dir=path.parent,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(updated_text)

        try:
            return validator.validate_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _persist_atomic(self, path: Path, updated_text: str) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=path.suffix,
            delete=False,
            dir=path.parent,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(updated_text)
        temp_path.replace(path)

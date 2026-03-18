from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.schemas.viewer import (
    FileViewAtLineRequest,
    FileViewError,
    FileViewRequest,
    FileViewResponse,
    VIEW_PAGE_SIZE,
)


@dataclass(slots=True)
class FileViewerState:
    current_start_line: int = 1


class FileViewerSessionManager:
    def __init__(self) -> None:
        self._states: dict[str, FileViewerState] = {}

    def open_file(self, request: FileViewRequest) -> FileViewResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_file(path)
        if validation_error is not None:
            return self._error_response(path, request.page_size, validation_error)

        state = self._states.setdefault(str(path.resolve()), FileViewerState())
        state.current_start_line = 1
        return self._build_response(path, start_line=state.current_start_line, page_size=request.page_size)

    def view_next(self, request: FileViewRequest) -> FileViewResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_file(path)
        if validation_error is not None:
            return self._error_response(path, request.page_size, validation_error)

        state = self._states.setdefault(str(path.resolve()), FileViewerState())
        total_line_count = self._read_lines(path)[1]
        if total_line_count <= request.page_size:
            state.current_start_line = 1
        else:
            state.current_start_line = min(
                total_line_count - request.page_size + 1,
                state.current_start_line + request.page_size,
            )
        return self._build_response(path, start_line=state.current_start_line, page_size=request.page_size)

    def view_prev(self, request: FileViewRequest) -> FileViewResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_file(path)
        if validation_error is not None:
            return self._error_response(path, request.page_size, validation_error)

        state = self._states.setdefault(str(path.resolve()), FileViewerState())
        state.current_start_line = max(1, state.current_start_line - request.page_size)
        return self._build_response(path, start_line=state.current_start_line, page_size=request.page_size)

    def view_at_line(self, request: FileViewAtLineRequest) -> FileViewResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_file(path)
        if validation_error is not None:
            return self._error_response(path, request.page_size, validation_error)

        _lines, total_line_count = self._read_lines(path)
        state = self._states.setdefault(str(path.resolve()), FileViewerState())
        state.current_start_line = self._clamp_start_line(
            requested_start=request.line,
            total_line_count=total_line_count,
            page_size=request.page_size,
        )
        return self._build_response(path, start_line=state.current_start_line, page_size=request.page_size)

    def view_centered(self, request: FileViewAtLineRequest) -> FileViewResponse:
        path = Path(request.file_path).expanduser()
        validation_error = self._validate_file(path)
        if validation_error is not None:
            return self._error_response(path, request.page_size, validation_error)

        _lines, total_line_count = self._read_lines(path)
        half_window = request.page_size // 2
        desired_start = max(1, request.line - half_window)
        state = self._states.setdefault(str(path.resolve()), FileViewerState())
        state.current_start_line = self._clamp_start_line(
            requested_start=desired_start,
            total_line_count=total_line_count,
            page_size=request.page_size,
        )
        return self._build_response(path, start_line=state.current_start_line, page_size=request.page_size)

    def _build_response(self, path: Path, *, start_line: int, page_size: int) -> FileViewResponse:
        lines, total_line_count = self._read_lines(path)
        if total_line_count == 0:
            return FileViewResponse(
                ok=True,
                file_path=str(path),
                current_start_line=1,
                current_end_line=0,
                total_line_count=0,
                page_size=page_size,
                lines=[],
            )

        end_line = min(total_line_count, start_line + page_size - 1)
        visible_lines = [
            self._format_line(line_number, lines[line_number - 1])
            for line_number in range(start_line, end_line + 1)
        ]
        return FileViewResponse(
            ok=True,
            file_path=str(path),
            current_start_line=start_line,
            current_end_line=end_line,
            total_line_count=total_line_count,
            page_size=page_size,
            lines=visible_lines,
        )

    def _read_lines(self, path: Path) -> tuple[list[str], int]:
        contents = path.read_text(encoding="utf-8")
        lines = contents.splitlines()
        return lines, len(lines)

    def _validate_file(self, path: Path) -> FileViewError | None:
        if not path.exists():
            return FileViewError(code="invalid_file", message=f"File does not exist: {path}")
        if not path.is_file():
            return FileViewError(code="invalid_file", message=f"Path is not a file: {path}")
        return None

    def _error_response(self, path: Path, page_size: int, error: FileViewError) -> FileViewResponse:
        return FileViewResponse(
            ok=False,
            file_path=str(path),
            current_start_line=1,
            current_end_line=0,
            total_line_count=0,
            page_size=page_size,
            lines=[],
            error=error,
        )

    def _clamp_start_line(self, *, requested_start: int, total_line_count: int, page_size: int) -> int:
        if total_line_count <= page_size:
            return 1
        max_start = total_line_count - page_size + 1
        return max(1, min(requested_start, max_start))

    def _format_line(self, line_number: int, line_text: str) -> str:
        return f"{line_number}|{line_text}"


_DEFAULT_MANAGER = FileViewerSessionManager()


def open_file(path: str) -> FileViewResponse:
    return _DEFAULT_MANAGER.open_file(FileViewRequest(file_path=path, page_size=VIEW_PAGE_SIZE))


def view_next(path: str) -> FileViewResponse:
    return _DEFAULT_MANAGER.view_next(FileViewRequest(file_path=path, page_size=VIEW_PAGE_SIZE))


def view_prev(path: str) -> FileViewResponse:
    return _DEFAULT_MANAGER.view_prev(FileViewRequest(file_path=path, page_size=VIEW_PAGE_SIZE))


def view_at_line(path: str, line: int) -> FileViewResponse:
    return _DEFAULT_MANAGER.view_at_line(
        FileViewAtLineRequest(file_path=path, line=line, page_size=VIEW_PAGE_SIZE)
    )


def view_centered(path: str, line: int) -> FileViewResponse:
    return _DEFAULT_MANAGER.view_centered(
        FileViewAtLineRequest(file_path=path, line=line, page_size=VIEW_PAGE_SIZE)
    )

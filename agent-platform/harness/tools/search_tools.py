from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from harness.schemas.search import (
    FileMatch,
    FindFileRequest,
    FindFileResponse,
    RESULT_LIMIT,
    SearchDirRequest,
    SearchDirResponse,
    SearchError,
    SearchFileRequest,
    SearchFileResponse,
    TextMatch,
)


GLOB_CHARS = {"*", "?", "["}


def find_file(request: FindFileRequest) -> FindFileResponse:
    root = Path(request.root_path).expanduser()
    validation_error = _validate_directory(root)
    if validation_error is not None:
        return FindFileResponse(
            ok=False,
            scope_path=str(root),
            query=request.query,
            error=validation_error,
        )

    matcher = _build_file_matcher(request.query, case_sensitive=request.case_sensitive)
    all_matches: list[FileMatch] = []
    for candidate in _iter_files(root, include_hidden=request.include_hidden):
        relative_path = candidate.relative_to(root).as_posix()
        if matcher(relative_path, candidate.name):
            all_matches.append(
                FileMatch(
                    path=relative_path,
                    name=candidate.name,
                )
            )

    all_matches.sort(key=lambda match: (match.path, match.name))
    return _finalize_file_response(
        scope_path=str(root),
        query=request.query,
        results=all_matches,
        result_limit=request.result_limit,
    )


def search_file(request: SearchFileRequest) -> SearchFileResponse:
    target_file = Path(request.file_path).expanduser()
    validation_error = _validate_file(target_file)
    if validation_error is not None:
        return SearchFileResponse(
            ok=False,
            scope_path=str(target_file),
            query=request.query,
            error=validation_error,
        )

    matches: list[TextMatch] = []
    needle = request.query if request.case_sensitive else request.query.lower()
    for line_number, line in enumerate(target_file.read_text(encoding="utf-8").splitlines(), start=1):
        haystack = line if request.case_sensitive else line.lower()
        if needle in haystack:
            matches.append(
                TextMatch(
                    path=target_file.name,
                    line_number=line_number,
                    line_text=line,
                )
            )

    return _finalize_text_response(
        response_type=SearchFileResponse,
        scope_path=str(target_file),
        query=request.query,
        results=matches,
        result_limit=request.result_limit,
    )


def search_dir(request: SearchDirRequest) -> SearchDirResponse:
    root = Path(request.root_path).expanduser()
    validation_error = _validate_directory(root)
    if validation_error is not None:
        return SearchDirResponse(
            ok=False,
            scope_path=str(root),
            query=request.query,
            error=validation_error,
        )

    matches: list[TextMatch] = []
    needle = request.query if request.case_sensitive else request.query.lower()
    for candidate in _iter_files(root, include_hidden=request.include_hidden):
        relative_path = candidate.relative_to(root).as_posix()
        for line_number, line in enumerate(candidate.read_text(encoding="utf-8").splitlines(), start=1):
            haystack = line if request.case_sensitive else line.lower()
            if needle in haystack:
                matches.append(
                    TextMatch(
                        path=relative_path,
                        line_number=line_number,
                        line_text=line,
                    )
                )

    matches.sort(key=lambda match: (match.path, match.line_number, match.line_text))
    return _finalize_text_response(
        response_type=SearchDirResponse,
        scope_path=str(root),
        query=request.query,
        results=matches,
        result_limit=request.result_limit,
    )


def _validate_directory(path: Path) -> SearchError | None:
    if not path.exists():
        return SearchError(code="invalid_path", message=f"Directory does not exist: {path}")
    if not path.is_dir():
        return SearchError(code="invalid_path", message=f"Path is not a directory: {path}")
    return None


def _validate_file(path: Path) -> SearchError | None:
    if not path.exists():
        return SearchError(code="invalid_path", message=f"File does not exist: {path}")
    if not path.is_file():
        return SearchError(code="invalid_path", message=f"Path is not a file: {path}")
    return None


def _iter_files(root: Path, *, include_hidden: bool):
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        if not include_hidden and _path_has_hidden_part(candidate.relative_to(root)):
            continue
        yield candidate


def _path_has_hidden_part(relative_path: Path) -> bool:
    return any(part.startswith(".") for part in relative_path.parts)


def _build_file_matcher(query: str, *, case_sensitive: bool):
    normalized_query = query if case_sensitive else query.lower()
    uses_glob = any(char in query for char in GLOB_CHARS)

    def matcher(relative_path: str, file_name: str) -> bool:
        path_value = relative_path if case_sensitive else relative_path.lower()
        name_value = file_name if case_sensitive else file_name.lower()
        if uses_glob:
            return fnmatch(path_value, normalized_query) or fnmatch(name_value, normalized_query)
        return normalized_query in path_value or normalized_query in name_value

    return matcher


def _build_refinement_guidance(*, query: str, result_count: int) -> str:
    return (
        f"Query {query!r} matched {result_count} results. "
        "Narrow the search by using a more specific file name, directory, or exact text."
    )


def _finalize_file_response(
    *,
    scope_path: str,
    query: str,
    results: list[FileMatch],
    result_limit: int,
) -> FindFileResponse:
    if len(results) > result_limit:
        return FindFileResponse(
            ok=True,
            scope_path=scope_path,
            query=query,
            too_many_results=True,
            result_count=len(results),
            refinement_guidance=_build_refinement_guidance(query=query, result_count=len(results)),
            results=[],
        )
    return FindFileResponse(
        ok=True,
        scope_path=scope_path,
        query=query,
        too_many_results=False,
        result_count=len(results),
        refinement_guidance=None,
        results=results[:RESULT_LIMIT],
    )


def _finalize_text_response(
    *,
    response_type,
    scope_path: str,
    query: str,
    results: list[TextMatch],
    result_limit: int,
):
    if len(results) > result_limit:
        return response_type(
            ok=True,
            scope_path=scope_path,
            query=query,
            too_many_results=True,
            result_count=len(results),
            refinement_guidance=_build_refinement_guidance(query=query, result_count=len(results)),
            results=[],
        )
    return response_type(
        ok=True,
        scope_path=scope_path,
        query=query,
        too_many_results=False,
        result_count=len(results),
        refinement_guidance=None,
        results=results[:RESULT_LIMIT],
    )

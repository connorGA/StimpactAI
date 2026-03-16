from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

from api.core.config import get_repository_root
from models.failure_classification import FailureClassification
from models.incident import IncidentEventRecord, IncidentRecord, TelemetryRecord
from models.root_cause import CodeCandidate, CodeSnippet, GitSignal, RootCauseEvidence

_CODE_FILE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql"}
_IGNORED_PATH_PARTS = {".git", ".next", "node_modules", "__pycache__", ".venv"}
_STOPWORDS = {
    "while",
    "with",
    "from",
    "into",
    "that",
    "this",
    "have",
    "failed",
    "error",
    "traceback",
    "incident",
    "service",
}
_MAX_CODE_CANDIDATES = 5
_MAX_CODE_SNIPPETS = 3


class CodeContextService:
    def __init__(
        self,
        *,
        stack_parser: StackTraceParser | None = None,
        code_search: CodeSearchAdapter | None = None,
        snippet_retriever: SnippetRetriever | None = None,
        git_history: GitHistoryAdapter | None = None,
    ) -> None:
        repository_root = _resolve_repository_root(
            code_search=code_search,
            snippet_retriever=snippet_retriever,
            git_history=git_history,
        )
        self._stack_parser = stack_parser or StackTraceParser()
        self._code_search = code_search or CodeSearchAdapter(repository_root)
        self._snippet_retriever = snippet_retriever or SnippetRetriever(repository_root)
        self._git_history = git_history or GitHistoryAdapter(repository_root)

    def build_evidence(
        self,
        *,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
        classification: FailureClassification,
        latest_telemetry: TelemetryRecord,
    ) -> RootCauseEvidence:
        stack_signals = self._stack_parser.extract_signals(events)
        search_terms = self._build_search_terms(
            incident=incident,
            events=events,
            classification=classification,
            stack_signals=stack_signals,
        )
        code_candidates = self._code_search.search(
            incident=incident,
            stack_signals=stack_signals,
            search_terms=search_terms,
            classification=classification,
        )
        code_snippets = self._snippet_retriever.retrieve(
            code_candidates=code_candidates,
            search_terms=search_terms,
        )
        git_signals = self._git_history.inspect(
            code_candidates=code_candidates,
            latest_commit_sha=latest_telemetry.commit_sha,
        )

        suspected_component = code_candidates[0].file_path if code_candidates else None
        evidence_confidence = self._score_evidence(
            stack_signals=stack_signals,
            code_candidates=code_candidates,
            code_snippets=code_snippets,
            git_signals=git_signals,
        )
        evidence_summary = self._build_evidence_summary(
            incident=incident,
            classification=classification,
            stack_signals=stack_signals,
            code_candidates=code_candidates,
            code_snippets=code_snippets,
            git_signals=git_signals,
        )

        return RootCauseEvidence(
            suspected_component=suspected_component,
            evidence_summary=evidence_summary,
            stack_trace_signals=stack_signals,
            search_terms=search_terms,
            code_candidates=code_candidates,
            code_snippets=code_snippets,
            git_signals=git_signals,
            evidence_confidence=evidence_confidence,
            latest_commit_sha=latest_telemetry.commit_sha,
            inspected_event_count=len(events),
        )

    def _build_search_terms(
        self,
        *,
        incident: IncidentRecord,
        events: Sequence[IncidentEventRecord],
        classification: FailureClassification,
        stack_signals: Sequence[str],
    ) -> list[str]:
        terms: list[str] = []
        terms.extend(stack_signals)
        terms.extend(classification.matched_signals)
        terms.extend(part for part in re.split(r"[-_]", incident.service.lower()) if part)

        for event in events[:3]:
            terms.extend(
                token
                for token in re.findall(r"[a-zA-Z_]{4,}", event.error_message.lower())
                if token not in _STOPWORDS
            )

        unique_terms: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = term.strip().strip("\"'").lower()
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            unique_terms.append(normalized)

        return unique_terms[:12]

    def _score_evidence(
        self,
        *,
        stack_signals: Sequence[str],
        code_candidates: Sequence[CodeCandidate],
        code_snippets: Sequence[CodeSnippet],
        git_signals: Sequence[GitSignal],
    ) -> float:
        score = 0.2
        if stack_signals:
            score += 0.25
        if code_candidates:
            score += min(0.2, code_candidates[0].confidence * 0.25)
        if code_snippets:
            score += min(0.2, code_snippets[0].confidence * 0.25)
        if git_signals:
            score += 0.1
        return min(0.95, round(score, 2))

    def _build_evidence_summary(
        self,
        *,
        incident: IncidentRecord,
        classification: FailureClassification,
        stack_signals: Sequence[str],
        code_candidates: Sequence[CodeCandidate],
        code_snippets: Sequence[CodeSnippet],
        git_signals: Sequence[GitSignal],
    ) -> str:
        summary_parts = [
            f"The incident is currently classified as {classification.category.value.replace('_', ' ')}.",
        ]
        if stack_signals:
            summary_parts.append(f"Stack trace signals point toward {', '.join(stack_signals[:3])}.")
        if code_candidates:
            summary_parts.append(
                f"Code search ranked {code_candidates[0].file_path} as the top candidate area."
            )
        if code_snippets:
            summary_parts.append("Relevant code snippets were extracted from the highest-confidence matches.")
        if git_signals:
            summary_parts.append("Recent git history also touched the leading candidate area.")
        if not code_candidates:
            summary_parts.append(
                f"No strong code candidate was found yet for the {incident.service} incident."
            )
        return " ".join(summary_parts)


class StackTraceParser:
    _python_pattern = re.compile(r'File "([^"]+)", line \d+, in ([A-Za-z_][A-Za-z0-9_]*)')
    _js_pattern = re.compile(
        r"at (?:(?:new )?([A-Za-z_$][A-Za-z0-9_$.<>]*) )?\(?([^()\s]+?\.(?:ts|tsx|js|jsx|py)):\d+(?::\d+)?\)?"
    )

    def extract_signals(self, events: Sequence[IncidentEventRecord]) -> list[str]:
        signals: list[str] = []
        for event in events:
            stacktrace = event.stacktrace or ""
            for file_path, function_name in self._python_pattern.findall(stacktrace):
                signals.append(Path(file_path).name)
                signals.append(function_name)
            for function_name, file_path in self._js_pattern.findall(stacktrace):
                signals.append(Path(file_path).name)
                if function_name:
                    signals.append(function_name.split(".")[-1])

        unique_signals: list[str] = []
        seen: set[str] = set()
        for signal in signals:
            normalized = signal.strip().strip("\"'").lower()
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            unique_signals.append(normalized)
        return unique_signals[:8]


class CodeSearchAdapter:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    def search(
        self,
        *,
        incident: IncidentRecord,
        stack_signals: Sequence[str],
        search_terms: Sequence[str],
        classification: FailureClassification,
    ) -> list[CodeCandidate]:
        if not self._repository_root.exists():
            return []

        filename_terms = {term for term in stack_signals if "." in term}
        symbol_terms = {term for term in stack_signals if "." not in term}
        service_terms = {
            part.lower()
            for part in re.split(r"[-_]", incident.service)
            if part and len(part) >= 3
        }
        classification_terms = set(classification.matched_signals)

        candidates: list[tuple[float, CodeCandidate]] = []
        for path in self._iter_code_files():
            rel_path = path.relative_to(self._repository_root).as_posix()
            rel_path_lower = rel_path.lower()
            file_name_lower = path.name.lower()

            matched_terms: list[str] = []
            score = 0.0
            reasons: list[str] = []

            filename_hits = [term for term in filename_terms if term in file_name_lower or term in rel_path_lower]
            if filename_hits:
                matched_terms.extend(filename_hits)
                score += 0.55
                reasons.append("stack trace file match")

            path_service_hits = [term for term in service_terms if term in rel_path_lower]
            if path_service_hits:
                matched_terms.extend(path_service_hits)
                score += 0.1
                reasons.append("service path match")

            if score <= 0.0 and not symbol_terms and not classification_terms and not search_terms:
                continue

            content = _read_text_file(path)
            if not content:
                continue
            content_lower = content.lower()

            symbol_hits = [term for term in symbol_terms if term in content_lower]
            if symbol_hits:
                matched_terms.extend(symbol_hits)
                score += min(0.25, 0.12 * len(symbol_hits))
                reasons.append("stack symbol match")

            classification_hits = [term for term in classification_terms if term in content_lower]
            if classification_hits:
                matched_terms.extend(classification_hits)
                score += min(0.12, 0.06 * len(classification_hits))
                reasons.append("classification signal match")

            search_hits = [term for term in search_terms if term in content_lower][:4]
            if search_hits:
                matched_terms.extend(search_hits)
                score += min(0.15, 0.04 * len(search_hits))
                reasons.append("error keyword match")

            if score < 0.2:
                continue

            unique_terms = list(dict.fromkeys(matched_terms))
            symbol = next((term for term in unique_terms if term in symbol_terms), None)
            candidate = CodeCandidate(
                file_path=rel_path,
                symbol=symbol,
                match_reason=", ".join(dict.fromkeys(reasons)),
                matched_terms=unique_terms[:6],
                confidence=min(0.99, round(score, 2)),
            )
            candidates.append((score, candidate))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates[:_MAX_CODE_CANDIDATES]]

    def _iter_code_files(self) -> Iterable[Path]:
        for path in self._repository_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _CODE_FILE_EXTENSIONS:
                continue
            if any(part in _IGNORED_PATH_PARTS for part in path.parts):
                continue
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            yield path


class SnippetRetriever:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    def retrieve(
        self,
        *,
        code_candidates: Sequence[CodeCandidate],
        search_terms: Sequence[str],
    ) -> list[CodeSnippet]:
        snippets: list[CodeSnippet] = []

        for candidate in code_candidates[:_MAX_CODE_SNIPPETS]:
            path = self._repository_root / candidate.file_path
            content = _read_text_file(path)
            if not content:
                continue

            lines = content.splitlines()
            focus_line = self._find_focus_line(
                lines=lines,
                candidate=candidate,
                search_terms=search_terms,
            )
            start_line = max(1, focus_line - 5)
            end_line = min(len(lines), focus_line + 6)
            snippet_content = "\n".join(lines[start_line - 1 : end_line]).strip()
            if not snippet_content:
                continue

            snippets.append(
                CodeSnippet(
                    file_path=candidate.file_path,
                    symbol=candidate.symbol,
                    start_line=start_line,
                    end_line=end_line,
                    content=snippet_content,
                    match_reason=candidate.match_reason,
                    confidence=candidate.confidence,
                )
            )

        return snippets

    def _find_focus_line(
        self,
        *,
        lines: Sequence[str],
        candidate: CodeCandidate,
        search_terms: Sequence[str],
    ) -> int:
        focus_terms = [term for term in [candidate.symbol, *candidate.matched_terms, *search_terms] if term]
        lowered_terms = [term.lower() for term in focus_terms]

        for index, line in enumerate(lines, start=1):
            normalized = line.lower()
            if any(term in normalized for term in lowered_terms):
                return index

        return 1


class GitHistoryAdapter:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    def inspect(
        self,
        *,
        code_candidates: Sequence[CodeCandidate],
        latest_commit_sha: str | None,
    ) -> list[GitSignal]:
        if not self._is_git_repo():
            return []

        signals: list[GitSignal] = []
        seen: set[tuple[str, str]] = set()

        for candidate in code_candidates[:3]:
            for commit_sha, committed_at, summary in self._recent_commits_for_path(candidate.file_path):
                key = (candidate.file_path, commit_sha)
                if key in seen:
                    continue
                seen.add(key)
                reason = "recent commit touched a top code candidate"
                if latest_commit_sha and commit_sha.startswith(latest_commit_sha[:8]):
                    reason = "latest telemetry commit also touched a top code candidate"
                signals.append(
                    GitSignal(
                        file_path=candidate.file_path,
                        commit_sha=commit_sha,
                        commit_summary=summary,
                        committed_at=committed_at,
                        relevance_reason=reason,
                    )
                )

        return signals[:5]

    def _is_git_repo(self) -> bool:
        if not self._repository_root.exists():
            return False
        result = subprocess.run(
            ["git", "-C", str(self._repository_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _recent_commits_for_path(self, file_path: str) -> list[tuple[str, datetime | None, str]]:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self._repository_root),
                "log",
                "--format=%H%x09%ct%x09%s",
                "-n",
                "3",
                "--",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        commits: list[tuple[str, datetime | None, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            sha, timestamp, summary = parts
            committed_at = None
            if timestamp.isdigit():
                committed_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
            commits.append((sha, committed_at, summary))
        return commits


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _resolve_repository_root(
    *,
    code_search: CodeSearchAdapter | None,
    snippet_retriever: SnippetRetriever | None,
    git_history: GitHistoryAdapter | None,
) -> Path:
    for adapter in (code_search, snippet_retriever, git_history):
        if adapter is not None:
            return adapter.repository_root
    return get_repository_root()

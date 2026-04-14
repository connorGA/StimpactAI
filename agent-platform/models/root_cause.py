from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.failure_classification import FailureCategory


class CodeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    symbol: str | None = None
    match_reason: str
    matched_terms: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class GitSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    commit_sha: str
    commit_summary: str
    committed_at: datetime | None = None
    relevance_reason: str


class CodeSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    symbol: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    match_reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class RootCauseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suspected_component: str | None = None
    evidence_summary: str
    stack_trace_signals: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    code_candidates: list[CodeCandidate] = Field(default_factory=list)
    code_snippets: list[CodeSnippet] = Field(default_factory=list)
    git_signals: list[GitSignal] = Field(default_factory=list)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    latest_commit_sha: str | None = None
    inspected_event_count: int = Field(ge=0)


class RootCauseReasoning(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root_cause_hypothesis: str
    reasoning_summary: str
    alternative_hypotheses: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("root_cause_hypothesis", "reasoning_summary", mode="before")
    @classmethod
    def _coerce_list_to_str(cls, v: Any) -> str:
        if isinstance(v, list):
            return " ".join(str(item) for item in v)
        return v


class RootCauseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    category: FailureCategory
    category_summary: str
    category_confidence: float = Field(ge=0.0, le=1.0)
    evidence: RootCauseEvidence
    reasoning: RootCauseReasoning

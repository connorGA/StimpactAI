from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


RESULT_LIMIT = 50


class SearchRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: str = Field(min_length=1, max_length=4096)
    query: str = Field(min_length=1, max_length=512)
    result_limit: int = Field(default=RESULT_LIMIT, ge=1, le=RESULT_LIMIT)
    include_hidden: bool = False

    @field_validator("root_path", "query")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class FindFileRequest(SearchRequestBase):
    case_sensitive: bool = False


class SearchDirRequest(SearchRequestBase):
    case_sensitive: bool = False


class SearchFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=4096)
    query: str = Field(min_length=1, max_length=512)
    result_limit: int = Field(default=RESULT_LIMIT, ge=1, le=RESULT_LIMIT)
    case_sensitive: bool = False

    @field_validator("file_path", "query")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class SearchError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class SearchResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    scope_path: str
    query: str
    too_many_results: bool = False
    result_count: int = 0
    refinement_guidance: str | None = None
    error: SearchError | None = None


class FileMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    name: str


class TextMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    line_number: int = Field(ge=1)
    line_text: str


class FindFileResponse(SearchResponseBase):
    results: list[FileMatch] = Field(default_factory=list)


class SearchFileResponse(SearchResponseBase):
    results: list[TextMatch] = Field(default_factory=list)


class SearchDirResponse(SearchResponseBase):
    results: list[TextMatch] = Field(default_factory=list)

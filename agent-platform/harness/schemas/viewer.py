from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


VIEW_PAGE_SIZE = 100


class FileViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=4096)
    page_size: int = Field(default=VIEW_PAGE_SIZE, ge=1, le=VIEW_PAGE_SIZE)

    @field_validator("page_size", mode="before")
    @classmethod
    def normalize_page_size(cls, value: object) -> object:
        if value is None:
            return VIEW_PAGE_SIZE
        if isinstance(value, int):
            return min(value, VIEW_PAGE_SIZE)
        return value

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("file_path must not be blank")
        return normalized


class FileViewAtLineRequest(FileViewRequest):
    line: int = Field(ge=1)


class FileViewError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class FileViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    file_path: str
    current_start_line: int = Field(ge=1, default=1)
    current_end_line: int = Field(ge=0, default=0)
    total_line_count: int = Field(ge=0, default=0)
    page_size: int = Field(ge=1, le=VIEW_PAGE_SIZE)
    lines: list[str] = Field(default_factory=list)
    error: FileViewError | None = None

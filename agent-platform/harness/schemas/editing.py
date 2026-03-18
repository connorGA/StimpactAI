from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EditFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=4096)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    replacement_text: str = Field(max_length=100_000)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("file_path must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_line_range(self) -> "EditFileRequest":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ValidationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    output: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    language: str
    validator: str
    output: str = ""
    message: str | None = None


class EditError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class EditFileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    changed_region_summary: str | None = None
    original_code: str = ""
    replacement_text: str = ""
    validation: ValidationResult | None = None
    validation_failure: ValidationFailure | None = None
    error: EditError | None = None

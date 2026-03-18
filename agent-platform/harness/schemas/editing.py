from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EditFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1, max_length=4096)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    replacement_text: str = Field(max_length=100_000)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_string_replacement_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if {"start_line", "end_line", "replacement_text"} <= set(data):
            return data
        if "new_content" in data:
            file_path = data.get("file_path")
            new_content = data.get("new_content")
            if not isinstance(file_path, str) or not file_path.strip():
                raise ValueError("file_path is required when using new_content edit arguments")
            if not isinstance(new_content, str):
                raise ValueError("new_content must be a string")

            path = Path(file_path).expanduser()
            if not path.exists() or not path.is_file():
                raise ValueError(f"File does not exist: {path}")

            original_text = path.read_text(encoding="utf-8")
            line_count = max(1, len(original_text.splitlines()))
            normalized = dict(data)
            normalized["start_line"] = 1
            normalized["end_line"] = line_count
            normalized["replacement_text"] = new_content
            normalized.pop("new_content", None)
            return normalized
        if "edits" in data:
            edits = data.get("edits")
            if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
                raise ValueError("edits must contain exactly one edit object when using batch edit arguments")
            edit = edits[0]
            normalized = dict(data)
            normalized.pop("edits", None)
            if "old_text" in edit:
                normalized["old_string"] = edit.get("old_text")
            if "new_text" in edit:
                normalized["new_string"] = edit.get("new_text")
            if "replacement_text" in edit and "new_string" not in normalized:
                normalized["new_string"] = edit.get("replacement_text")
            return cls.normalize_legacy_string_replacement_shape(normalized)
        if "old_string" not in data or "new_string" not in data:
            return data

        file_path = data.get("file_path")
        old_string = data.get("old_string")
        new_string = data.get("new_string")
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("file_path is required when using old_string/new_string edit arguments")
        if not isinstance(old_string, str) or not isinstance(new_string, str):
            raise ValueError("old_string and new_string must be strings")

        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            raise ValueError(f"File does not exist: {path}")

        contents = path.read_text(encoding="utf-8")
        occurrences = contents.count(old_string)
        if occurrences != 1:
            raise ValueError(
                "old_string must match exactly one region in the target file when using legacy edit arguments"
            )

        start_offset = contents.index(old_string)
        start_line = contents[:start_offset].count("\n") + 1
        line_count = len(old_string.splitlines()) or 1
        end_line = start_line + line_count - 1
        normalized = dict(data)
        normalized["start_line"] = start_line
        normalized["end_line"] = end_line
        normalized["replacement_text"] = new_string
        normalized.pop("old_string", None)
        normalized.pop("new_string", None)
        return normalized

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

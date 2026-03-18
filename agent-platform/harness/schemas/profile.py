from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BrowserVerificationEntrypoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=1000)
    ready_selector: str | None = Field(default=None, max_length=512)

    @field_validator("name", "url")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class HarnessRepositoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str | None = Field(default=None, max_length=4096)
    install_command: str | None = Field(default=None, max_length=4000)
    build_command: str | None = Field(default=None, max_length=4000)
    test_command: str | None = Field(default=None, max_length=4000)
    start_command: str | None = Field(default=None, max_length=4000)
    browser_verification_entrypoints: list[BrowserVerificationEntrypoint] = Field(default_factory=list)
    environment_assumptions: list[str] = Field(default_factory=list)
    ignored_directories: list[str] = Field(default_factory=list)
    language_hints: dict[str, str] = Field(default_factory=dict)

    @field_validator("install_command", "build_command", "test_command", "start_command")
    @classmethod
    def normalize_optional_commands(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("command values must not be blank")
        return normalized

    @field_validator("environment_assumptions", "ignored_directories")
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        return normalized

    @field_validator("language_hints")
    @classmethod
    def normalize_language_hints(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            normalized_key = key.strip()
            normalized_value = item.strip()
            if normalized_key and normalized_value:
                normalized[normalized_key] = normalized_value
        return normalized

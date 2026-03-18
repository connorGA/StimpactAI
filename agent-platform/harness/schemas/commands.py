from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=8_000)
    working_directory: str | None = Field(default=None, max_length=4_096)
    timeout_seconds: int = Field(default=120, ge=1, le=1_800)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("command must not be blank")
        return normalized

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("working_directory must not be blank when provided")
        return normalized

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            env_key = str(key).strip()
            if not env_key:
                raise ValueError("env keys must not be blank")
            normalized[env_key] = str(item)
        return normalized


class RunCommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    command: str = Field(min_length=1, max_length=8_000)
    working_directory: str = Field(min_length=1, max_length=4_096)
    exit_code: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    message: str | None = Field(default=None, max_length=1_000)

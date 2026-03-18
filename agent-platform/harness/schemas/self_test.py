from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from harness.schemas.verification import VerificationStatus


class HarnessSelfTestStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    ok: bool
    details: str = Field(min_length=1, max_length=2000)


class HarnessSelfTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    repository_root: str = Field(min_length=1, max_length=4096)
    init_script_path: str = Field(min_length=1, max_length=4096)
    features_path: str = Field(min_length=1, max_length=4096)
    checkpoint_ref: str = Field(min_length=1, max_length=256)
    diff_file_paths: list[str] = Field(default_factory=list)
    feature_id: str = Field(min_length=1, max_length=128)
    feature_verification_status: VerificationStatus
    context_preview: str = Field(min_length=1, max_length=5000)
    step_results: list[HarnessSelfTestStepResult] = Field(default_factory=list)

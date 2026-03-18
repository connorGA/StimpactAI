from __future__ import annotations

from pathlib import Path

from harness.self_test.runner import HarnessSelfTestRunner
from harness.schemas.verification import VerificationStatus


def test_harness_self_test_runner_executes_end_to_end_scenario(tmp_path: Path) -> None:
    runner = HarnessSelfTestRunner()

    result = runner.run(working_directory=str(tmp_path))

    assert result.ok is True
    assert Path(result.repository_root).exists()
    assert Path(result.init_script_path).exists()
    assert Path(result.features_path).exists()
    assert result.checkpoint_ref.startswith("stimpact-checkpoint/")
    assert "site/app.js" in result.diff_file_paths
    assert result.feature_verification_status is VerificationStatus.FULLY_VERIFIED
    assert len(result.step_results) >= 6
    assert all(step.ok for step in result.step_results)
    assert "guarded edit" in result.context_preview.lower()
    assert "verified the updated greeting in the browser" in result.context_preview.lower()

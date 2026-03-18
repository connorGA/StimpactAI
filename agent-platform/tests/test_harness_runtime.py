from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harness.schemas.initializer import FeatureCatalog, FeatureRecord, FeatureStatus, GitCheckpointStrategy, InitScriptOutput
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.context import ContextEvent, ContextEventKind
from harness.schemas.runtime import HarnessAgentRole, RuntimeSessionStatus, InitializerOutputContract
from harness.schemas.verification import FeatureVerificationState, VerificationKind, VerificationStatus
from harness.runtime.session import HarnessRuntime


def build_initializer_output() -> InitializerOutputContract:
    return InitializerOutputContract(
        repository_root="/repo",
        repository_profile=HarnessRepositoryProfile(
            install_command="python -m pip install -r requirements-dev.txt",
            build_command="npm run build",
            test_command="python -m pytest",
            start_command="npm run dev",
            environment_assumptions=["Use Python 3.13"],
            ignored_directories=[".git", "node_modules"],
            language_hints={".py": "python"},
        ),
        summary="Initializer discovered the install and start workflow.",
        init_script=InitScriptOutput(
            path="init.sh",
            content="#!/usr/bin/env bash\nset -euo pipefail\n",
        ),
        feature_catalog=FeatureCatalog(
            generated_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            repository_root="/repo",
            features=[
                FeatureRecord(
                    id="dashboard-loads",
                    feature_name="dashboard loads",
                    description="User can load the dashboard summary page.",
                    status=FeatureStatus.UNVERIFIED,
                    verification_method="Browser smoke test",
                    required_verification=[VerificationKind.UNIT, VerificationKind.BROWSER],
                    verification_state=FeatureVerificationState(
                        status=VerificationStatus.UNVERIFIED,
                        attempted=[],
                        passed=[],
                        remaining=[VerificationKind.UNIT, VerificationKind.BROWSER],
                        browser_required=True,
                        can_mark_complete=False,
                        completion_blockers=["Code compiles or lower-level checks passed, but browser verification still required."],
                    ),
                    notes=[],
                )
            ],
        ),
        checkpoint_strategy=GitCheckpointStrategy(
            checkpoint_message_prefix="stimpact checkpoint:",
            last_known_good_tag_prefix="stimpact-checkpoint/",
            reset_command_summary="Hard reset and clean back to the checkpoint.",
            notes=[],
        ),
        environment_notes=["Use Python 3.13", "Requires local Postgres"],
        recommended_commands=["pip install -r requirements.txt", "npm install"],
        known_constraints=["Sandbox access required for browser checks"],
        generated_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
    )


def test_runtime_assigns_distinct_role_permissions_and_prompts() -> None:
    runtime = HarnessRuntime()

    initializer = runtime.start_session(
        role=HarnessAgentRole.INITIALIZER,
        repository_root="/repo",
        objective="Scaffold the environment",
    )
    coding = runtime.start_session(
        role=HarnessAgentRole.CODING,
        repository_root="/repo",
        objective="Implement the fix",
    )

    assert initializer.role is HarnessAgentRole.INITIALIZER
    assert initializer.permissions.can_scaffold_environment is True
    assert initializer.permissions.can_modify_files is False
    assert "Initializer Agent" in initializer.prompt_template
    initializer_primitives = runtime.get_runtime_primitives(initializer.id)
    assert initializer_primitives.browser_tools is not None
    assert initializer_primitives.repository_profile is not None
    assert initializer_primitives.initializer_output_builder is not None
    assert initializer_primitives.git_checkpoint_manager is not None
    assert initializer_primitives.verification_rules_engine is not None

    assert coding.role is HarnessAgentRole.CODING
    assert coding.permissions.can_modify_files is True
    assert coding.permissions.can_run_verification is True
    assert "Coding Agent" in coding.prompt_template


def test_runtime_persists_initializer_output_for_later_sessions() -> None:
    runtime = HarnessRuntime()
    initializer = runtime.start_session(
        role=HarnessAgentRole.INITIALIZER,
        repository_root="/repo",
        objective="Scaffold the environment",
    )
    persisted = runtime.persist_initializer_output(initializer.id, build_initializer_output())

    assert persisted.initializer_output is not None
    assert persisted.initializer_output.summary.startswith("Initializer discovered")
    assert runtime.get_session(initializer.id) is not None


def test_runtime_builds_coding_agent_input_from_initializer_output_and_context() -> None:
    runtime = HarnessRuntime()
    initializer = runtime.start_session(
        role=HarnessAgentRole.INITIALIZER,
        repository_root="/repo",
        objective="Scaffold the environment",
    )
    runtime.persist_initializer_output(initializer.id, build_initializer_output())

    coding = runtime.start_session(
        role=HarnessAgentRole.CODING,
        repository_root="/repo",
        objective="Fix login flow",
    )
    primitives = runtime.get_runtime_primitives(coding.id)
    primitives.context_manager.record_event(
        ContextEvent(
            turn_id=1,
            kind=ContextEventKind.ACTION,
            summary="Reviewed initializer output",
            tool_output="Loaded recommended commands",
            repo_state="feature branch created",
        )
    )

    coding_input = runtime.build_coding_agent_input(
        initializer_session_id=initializer.id,
        coding_session_id=coding.id,
    )

    assert coding_input.initializer_output.summary.startswith("Initializer discovered")
    assert coding_input.current_objective == "Fix login flow"
    assert coding_input.context_packet.current_repo_state == "feature branch created"
    assert "Reviewed initializer output" in coding_input.context_packet.rendered_context


def test_runtime_requires_initializer_output_before_coding_handoff() -> None:
    runtime = HarnessRuntime()
    initializer = runtime.start_session(
        role=HarnessAgentRole.INITIALIZER,
        repository_root="/repo",
    )
    coding = runtime.start_session(
        role=HarnessAgentRole.CODING,
        repository_root="/repo",
    )

    with pytest.raises(ValueError):
        runtime.build_coding_agent_input(
            initializer_session_id=initializer.id,
            coding_session_id=coding.id,
        )


def test_runtime_can_pause_and_complete_sessions() -> None:
    runtime = HarnessRuntime()
    coding = runtime.start_session(
        role=HarnessAgentRole.CODING,
        repository_root="/repo",
    )

    paused = runtime.pause_session(coding.id)
    completed = runtime.complete_session(coding.id)

    assert paused.status is RuntimeSessionStatus.PAUSED
    assert completed.status is RuntimeSessionStatus.COMPLETED

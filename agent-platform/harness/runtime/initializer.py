from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from harness.runtime.profile import HarnessProfileLoader
from harness.runtime.verification import VerificationRulesEngine
from harness.schemas.initializer import (
    FeatureCatalog,
    FeatureRecord,
    FeatureSeed,
    FeatureStatus,
    GitCheckpointStrategy,
    InitScriptOutput,
)
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.runtime import InitializerOutputContract
from harness.schemas.verification import VerificationKind


class InitializerOutputBuilder:
    def __init__(self, *, profile_loader: HarnessProfileLoader | None = None) -> None:
        self._profile_loader = profile_loader or HarnessProfileLoader()

    def build_output(
        self,
        *,
        repository_root: str,
        summary: str,
        repository_profile: HarnessRepositoryProfile | None = None,
        feature_seeds: list[FeatureSeed] | None = None,
        environment_notes: list[str] | None = None,
        known_constraints: list[str] | None = None,
    ) -> InitializerOutputContract:
        root = Path(repository_root).resolve()
        generated_at = datetime.now(UTC)
        verification_engine = VerificationRulesEngine()
        profile = repository_profile or self._profile_loader.load_profile(repository_root=str(root))
        notes = list(profile.environment_assumptions) + (environment_notes or [])
        constraints = known_constraints or []
        recommended_commands = self._recommended_commands(root, profile)

        return InitializerOutputContract(
            repository_root=str(root),
            repository_profile=profile,
            summary=summary,
            init_script=InitScriptOutput(
                path="init.sh",
                content=self._build_init_script(root, notes, recommended_commands, profile),
            ),
            feature_catalog=FeatureCatalog(
                generated_at=generated_at,
                repository_root=str(root),
                features=self._build_feature_catalog(
                    feature_seeds,
                    generated_at,
                    verification_engine,
                    profile,
                ),
            ),
            checkpoint_strategy=self._checkpoint_strategy(),
            environment_notes=notes,
            recommended_commands=recommended_commands,
            known_constraints=constraints,
            generated_at=generated_at,
        )

    def persist_output(
        self,
        *,
        repository_root: str,
        initializer_output: InitializerOutputContract,
    ) -> InitializerOutputContract:
        root = Path(repository_root).resolve()
        stimpact_dir = root / ".stimpactai"
        stimpact_dir.mkdir(parents=True, exist_ok=True)

        init_path = root / initializer_output.init_script.path
        init_path.write_text(initializer_output.init_script.content, encoding="utf-8")
        init_path.chmod(init_path.stat().st_mode | 0o111)

        feature_path = stimpact_dir / "features.json"
        feature_path.write_text(
            initializer_output.feature_catalog.model_dump_json(indent=2),
            encoding="utf-8",
        )

        return initializer_output

    def _build_feature_catalog(
        self,
        feature_seeds: list[FeatureSeed] | None,
        generated_at: datetime,
        verification_engine: VerificationRulesEngine,
        profile: HarnessRepositoryProfile,
    ) -> list[FeatureRecord]:
        seeds = feature_seeds or self._default_feature_seeds()
        features: list[FeatureRecord] = []
        for index, seed in enumerate(seeds, start=1):
            feature_id = self._slugify(seed.feature_name)
            if not feature_id:
                feature_id = f"feature-{index}"
            features.append(
                FeatureRecord(
                    id=feature_id,
                    feature_name=seed.feature_name,
                    description=seed.description,
                    status=FeatureStatus.UNVERIFIED,
                    verification_method=seed.verification_method,
                    reproduction_command=seed.reproduction_command,
                    verification_command=seed.verification_command
                    or self._default_verification_command(seed, profile),
                    required_verification=seed.required_verification,
                    verification_state=verification_engine.build_initial_state(
                        required_verification=seed.required_verification,
                        browser_required=seed.browser_required,
                    ),
                    last_verified_at=None,
                    notes=seed.notes,
                )
            )
        return features

    def _default_verification_command(
        self,
        seed: FeatureSeed,
        profile: HarnessRepositoryProfile,
    ) -> str | None:
        if not seed.required_verification:
            return None
        if seed.browser_required:
            return None
        return profile.test_command

    def _build_init_script(
        self,
        repository_root: Path,
        environment_notes: list[str],
        recommended_commands: list[str],
        profile: HarnessRepositoryProfile,
    ) -> str:
        lines = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            f'REPO_ROOT="{repository_root}"',
            'cd "$REPO_ROOT"',
            "",
            'echo "Bootstrapping repository at $REPO_ROOT"',
        ]

        if environment_notes:
            lines.extend(["", 'echo "Environment notes:"'])
            lines.extend([f'echo " - {self._shell_escape(note)}"' for note in environment_notes])

        if profile.install_command:
            lines.extend(
                [
                    "",
                    "# Install project dependencies as defined by the repository profile.",
                    profile.install_command,
                ]
            )
        elif (repository_root / "pyproject.toml").exists():
            lines.extend(
                [
                    "",
                    'if [ ! -d ".venv" ]; then',
                    '  python3 -m venv .venv',
                    "fi",
                    '. ".venv/bin/activate"',
                    "python -m pip install --upgrade pip",
                    'if [ -f "requirements-dev.txt" ]; then',
                    "  python -m pip install -r requirements-dev.txt",
                    "fi",
                    'if [ -f "requirements.txt" ]; then',
                    "  python -m pip install -r requirements.txt",
                    "fi",
                ]
            )

        if recommended_commands:
            lines.extend(["", 'echo "Suggested next commands:"'])
            lines.extend([f'echo " - {self._shell_escape(command)}"' for command in recommended_commands])

        lines.extend(
            [
                "",
                'echo "Bootstrap complete. Review the suggested commands above before running long-lived services."',
                "",
            ]
        )
        return "\n".join(lines)

    def _recommended_commands(
        self,
        repository_root: Path,
        profile: HarnessRepositoryProfile,
    ) -> list[str]:
        commands: list[str] = []
        for value in [
            profile.build_command,
            profile.test_command,
            profile.start_command,
        ]:
            if value and value not in commands:
                commands.append(value)
        for entrypoint in profile.browser_verification_entrypoints:
            commands.append(f"Browser verify: {entrypoint.name} -> {entrypoint.url}")
        if commands:
            return commands
        if (repository_root / "pyproject.toml").exists():
            commands.extend(
                [
                    ". .venv/bin/activate",
                    "python -m pytest",
                ]
            )
        if (repository_root / "package.json").exists():
            commands.append("npm test")
        if (repository_root / "client-ui" / "package.json").exists():
            commands.extend(
                [
                    "cd client-ui && npm test",
                    "cd client-ui && npm run dev",
                ]
            )
        if not commands:
            commands.append("Review repository-specific setup and verification commands manually.")
        return commands

    def _checkpoint_strategy(self) -> GitCheckpointStrategy:
        return GitCheckpointStrategy(
            checkpoint_message_prefix="stimpact checkpoint:",
            last_known_good_tag_prefix="stimpact-checkpoint/",
            reset_command_summary="Create a checkpoint commit before each attempt, then hard reset and clean back to the checkpoint if the attempt fails.",
            notes=[
                "Checkpoint creation is part of runtime discipline and should happen before any repair attempt.",
                "Resetting a failed attempt must return both tracked and untracked files to the last-known-good checkpoint.",
            ],
        )

    def _default_feature_seeds(self) -> list[FeatureSeed]:
        return [
            FeatureSeed(
                feature_name="bootstrap local environment",
                description="A developer can initialize dependencies and repo-specific tooling from a clean checkout.",
                verification_method="Run init.sh and confirm dependency installation completes successfully.",
                required_verification=[VerificationKind.UNIT],
                browser_required=False,
                notes=["Replace with product-specific end-to-end capabilities when initializer evidence is available."],
            ),
            FeatureSeed(
                feature_name="run automated verification",
                description="A developer can execute the primary automated verification path for the repository.",
                verification_method="Run the repository's recommended test command and capture pass/fail state.",
                required_verification=[VerificationKind.UNIT, VerificationKind.INTEGRATION],
                browser_required=False,
            ),
            FeatureSeed(
                feature_name="start local application services",
                description="A developer can start the main local development services needed to exercise the product.",
                verification_method="Run the primary local service start commands and confirm processes stay healthy.",
                required_verification=[VerificationKind.INTEGRATION, VerificationKind.BROWSER],
                browser_required=True,
            ),
        ]

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return normalized[:128]

    def _shell_escape(self, value: str) -> str:
        return value.replace('"', '\\"')

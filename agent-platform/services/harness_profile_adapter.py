from __future__ import annotations

from harness.runtime.profile import HarnessProfileLoader
from harness.schemas.profile import BrowserVerificationEntrypoint, HarnessRepositoryProfile
from models.control_plane import RepoProfileRecord


class HarnessControlPlaneProfileAdapter:
    def __init__(self, *, loader: HarnessProfileLoader | None = None) -> None:
        self._loader = loader or HarnessProfileLoader()

    def build_profile(
        self,
        *,
        repository_root: str,
        repo_profile: RepoProfileRecord | None,
    ) -> HarnessRepositoryProfile:
        base_profile = self._loader.load_profile(repository_root=repository_root)
        if repo_profile is None:
            return base_profile

        browser_entrypoints = list(base_profile.browser_verification_entrypoints)
        if repo_profile.startup_commands:
            browser_entrypoints.append(
                BrowserVerificationEntrypoint(
                    name="repo-profile-default",
                    url="http://127.0.0.1:3000",
                    description="Default browser verification entrypoint inferred from the active repo profile.",
                )
            )

        environment_assumptions = [
            *base_profile.environment_assumptions,
            f"Control-plane repo profile {repo_profile.id} is active for project {repo_profile.project_id}.",
        ]

        return base_profile.model_copy(
            update={
                "install_command": repo_profile.install_command or base_profile.install_command,
                "test_command": repo_profile.verify_command or base_profile.test_command,
                "start_command": " && ".join(repo_profile.startup_commands)
                if repo_profile.startup_commands
                else base_profile.start_command,
                "browser_verification_entrypoints": browser_entrypoints,
                "environment_assumptions": environment_assumptions,
            }
        )

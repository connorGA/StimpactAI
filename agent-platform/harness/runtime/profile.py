from __future__ import annotations

from pathlib import Path

import yaml

from harness.schemas.profile import HarnessRepositoryProfile


class HarnessProfileLoader:
    PROFILE_RELATIVE_PATH = ".stimpactai/profile.yml"

    def load_profile(self, *, repository_root: str) -> HarnessRepositoryProfile:
        root = Path(repository_root).resolve()
        profile_path = root / self.PROFILE_RELATIVE_PATH
        if profile_path.exists():
            loaded = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            profile = HarnessRepositoryProfile.model_validate(
                {
                    "source_path": str(profile_path),
                    **loaded,
                }
            )
            return profile
        return self._default_profile(root)

    def _default_profile(self, repository_root: Path) -> HarnessRepositoryProfile:
        has_pyproject = (repository_root / "pyproject.toml").exists()
        has_root_package = (repository_root / "package.json").exists()
        has_client_ui = (repository_root / "client-ui" / "package.json").exists()

        install_parts: list[str] = []
        if has_pyproject:
            install_parts.extend(
                [
                    "python3 -m venv .venv",
                    '. ".venv/bin/activate"',
                    "python -m pip install --upgrade pip",
                    'if [ -f "requirements-dev.txt" ]; then python -m pip install -r requirements-dev.txt; fi',
                    'if [ -f "requirements.txt" ]; then python -m pip install -r requirements.txt; fi',
                ]
            )
        if has_root_package:
            install_parts.append("npm install")
        if has_client_ui:
            install_parts.append("(cd client-ui && npm install)")

        start_command = None
        if has_root_package:
            start_command = "npm run dev"
        elif has_client_ui:
            start_command = "cd client-ui && npm run dev"

        test_parts: list[str] = []
        if has_pyproject:
            test_parts.append('. ".venv/bin/activate" && python -m pytest')
        if has_root_package:
            test_parts.append("npm test")
        elif has_client_ui:
            test_parts.append("cd client-ui && npm test")

        build_command = None
        if has_root_package:
            build_command = "npm run build"
        elif has_client_ui:
            build_command = "cd client-ui && npm run build"

        environment_assumptions: list[str] = []
        if has_pyproject:
            environment_assumptions.append("Python 3.12+ is available locally.")
        if has_root_package or has_client_ui:
            environment_assumptions.append("Node.js and npm are available locally.")

        ignored_directories = [
            ".git",
            ".venv",
            "node_modules",
            ".next",
            "dist",
            "build",
            "__pycache__",
        ]

        language_hints: dict[str, str] = {}
        if has_pyproject:
            language_hints.update(
                {
                    ".py": "python",
                }
            )
        if has_root_package or has_client_ui:
            language_hints.update(
                {
                    ".js": "javascript",
                    ".jsx": "javascript",
                    ".ts": "typescript",
                    ".tsx": "typescript",
                }
            )

        return HarnessRepositoryProfile(
            source_path=None,
            install_command=" && ".join(install_parts) if install_parts else None,
            build_command=build_command,
            test_command=" && ".join(test_parts) if test_parts else None,
            start_command=start_command,
            browser_verification_entrypoints=[],
            environment_assumptions=environment_assumptions,
            ignored_directories=ignored_directories,
            language_hints=language_hints,
        )

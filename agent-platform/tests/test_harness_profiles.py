from __future__ import annotations

from pathlib import Path

from harness.runtime.initializer import InitializerOutputBuilder
from harness.runtime.profile import HarnessProfileLoader
from harness.runtime.session import HarnessRuntime
from harness.schemas.profile import HarnessRepositoryProfile
from harness.schemas.runtime import HarnessAgentRole


def test_profile_loader_parses_repo_local_profile_yaml(tmp_path: Path) -> None:
    profile_dir = tmp_path / ".stimpactai"
    profile_dir.mkdir()
    (profile_dir / "profile.yml").write_text(
        """
install_command: python -m pip install -r requirements-dev.txt
build_command: npm run build
test_command: python -m pytest
start_command: npm run dev
browser_verification_entrypoints:
  - name: home
    url: http://127.0.0.1:3000/
    ready_selector: "#app"
environment_assumptions:
  - PostgreSQL is running
ignored_directories:
  - .git
  - node_modules
language_hints:
  ".py": python
  ".tsx": typescript
""".strip(),
        encoding="utf-8",
    )

    loader = HarnessProfileLoader()
    profile = loader.load_profile(repository_root=str(tmp_path))

    assert profile.install_command == "python -m pip install -r requirements-dev.txt"
    assert profile.start_command == "npm run dev"
    assert profile.browser_verification_entrypoints[0].name == "home"
    assert profile.ignored_directories == [".git", "node_modules"]
    assert profile.language_hints[".tsx"] == "typescript"
    assert profile.source_path is not None
    assert profile.source_path.endswith(".stimpactai/profile.yml")


def test_profile_loader_builds_default_profile_when_file_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    (tmp_path / "client-ui").mkdir()
    (tmp_path / "client-ui" / "package.json").write_text('{"name":"client-ui"}\n', encoding="utf-8")

    loader = HarnessProfileLoader()
    profile = loader.load_profile(repository_root=str(tmp_path))

    assert profile.source_path is None
    assert profile.install_command is not None
    assert "python3 -m venv .venv" in profile.install_command
    assert "(cd client-ui && npm install)" in profile.install_command
    assert profile.test_command is not None
    assert "python -m pytest" in profile.test_command
    assert profile.start_command == "npm run dev"
    assert ".py" in profile.language_hints
    assert ".tsx" in profile.language_hints


def test_initializer_output_builder_uses_repository_profile_commands_and_assumptions(tmp_path: Path) -> None:
    profile = HarnessRepositoryProfile(
        install_command="make install",
        build_command="make build",
        test_command="make test",
        start_command="make run",
        environment_assumptions=["Docker is available."],
        ignored_directories=["vendor"],
        language_hints={".go": "go"},
    )

    builder = InitializerOutputBuilder()
    output = builder.build_output(
        repository_root=str(tmp_path),
        repository_profile=profile,
        summary="Profile-driven initializer output.",
    )

    assert output.repository_profile.install_command == "make install"
    assert "make install" in output.init_script.content
    assert "make build" in output.recommended_commands
    assert "make test" in output.recommended_commands
    assert "make run" in output.recommended_commands
    assert "Docker is available." in output.environment_notes


def test_runtime_loads_repository_profile_before_starting_session(tmp_path: Path) -> None:
    profile_dir = tmp_path / ".stimpactai"
    profile_dir.mkdir()
    (profile_dir / "profile.yml").write_text(
        """
install_command: uv sync
test_command: uv run pytest
start_command: uv run uvicorn api.main:app
environment_assumptions:
  - uv is installed locally
ignored_directories:
  - .git
language_hints:
  ".py": python
""".strip(),
        encoding="utf-8",
    )

    runtime = HarnessRuntime()
    session = runtime.start_session(
        role=HarnessAgentRole.INITIALIZER,
        repository_root=str(tmp_path),
        objective="Load repo profile",
    )
    primitives = runtime.get_runtime_primitives(session.id)

    assert session.repository_profile.install_command == "uv sync"
    assert session.repository_profile.test_command == "uv run pytest"
    assert primitives.repository_profile.install_command == "uv sync"

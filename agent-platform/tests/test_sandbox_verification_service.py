from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from models.async_job import AsyncJobRecord, AsyncJobStatus, AsyncJobType
from models.control_plane import (
    RepoProfileRecord,
    RepoProfileSecretBindingRecord,
    RuntimeKind,
    SecretBackend,
    SecretRefRecord,
)
from models.incident import IncidentRecord, IncidentSeverity, IncidentStatus
from models.patch import PatchRunRecord, PatchRunStatus
from models.sandbox import SandboxRunRecord, SandboxRunStatus
from sandbox.kubernetes_runner import KubernetesJobStatus
from sandbox.runner import SecretBindingRef
from services.sandbox_verification import SandboxVerificationService
from shared.types.telemetry import Environment


class StubIncidentRepository:
    def __init__(self, incident: IncidentRecord) -> None:
        self.incident = incident

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        if incident_id == self.incident.id:
            return self.incident
        return None


class StubSandboxRepository:
    def __init__(self) -> None:
        self.runs: dict[str, SandboxRunRecord] = {}

    async def create_sandbox_run(self, **kwargs) -> SandboxRunRecord:
        now = datetime.now(UTC)
        run = SandboxRunRecord(
            id=f"sandbox-{len(self.runs) + 1}",
            incident_id=kwargs["incident_id"],
            patch_run_id=kwargs["patch_run_id"],
            repo_profile_id=kwargs["repo_profile_id"],
            async_job_id=kwargs["async_job_id"],
            status=kwargs["status"],
            executor_backend=kwargs["executor_backend"],
            external_job_id=kwargs.get("external_job_id"),
            install_command=kwargs.get("install_command"),
            reproduce_command=kwargs["reproduce_command"],
            verify_command=kwargs["verify_command"],
            reproduction_succeeded=kwargs["reproduction_succeeded"],
            patch_applied=kwargs["patch_applied"],
            verification_succeeded=kwargs["verification_succeeded"],
            summary=kwargs["summary"],
            execution_log=kwargs["execution_log"],
            created_at=now,
            updated_at=now,
        )
        self.runs[run.id] = run
        return run

    async def create_sandbox_run_step(self, **kwargs):
        return SimpleNamespace(**kwargs)

    async def create_sandbox_run_attempt(self, **kwargs):
        return SimpleNamespace(**kwargs)

    async def list_sandbox_runs(self, incident_id: str, *, limit: int = 20) -> list[SandboxRunRecord]:
        _ = limit
        return [run for run in self.runs.values() if run.incident_id == incident_id]

    async def list_active_kubernetes_runs(self, *, limit: int = 50) -> list[SandboxRunRecord]:
        _ = limit
        return [
            run
            for run in self.runs.values()
            if run.status is SandboxRunStatus.RUNNING
            and run.executor_backend == "kubernetes"
            and run.external_job_id is not None
        ]

    async def update_sandbox_run(self, sandbox_run_id: str, **kwargs) -> SandboxRunRecord:
        current = self.runs[sandbox_run_id]
        updated = current.model_copy(
            update={
                **kwargs,
                "updated_at": datetime.now(UTC),
            }
        )
        self.runs[sandbox_run_id] = updated
        return updated


class StubControlPlaneRepository:
    def __init__(
        self,
        repo_profile: RepoProfileRecord,
        secret_refs: list[SecretRefRecord] | None = None,
        secret_bindings: list[RepoProfileSecretBindingRecord] | None = None,
    ) -> None:
        self.repo_profile = repo_profile
        self.secret_refs = secret_refs or []
        self.secret_bindings = secret_bindings or [
            RepoProfileSecretBindingRecord(
                repo_profile_id=self.repo_profile.id,
                mount_as=secret_ref.label,
                secret_ref=secret_ref,
                created_at=secret_ref.created_at,
            )
            for secret_ref in self.secret_refs
        ]

    async def get_active_repo_profile(self, project_id: str) -> RepoProfileRecord | None:
        if project_id == self.repo_profile.project_id:
            return self.repo_profile
        return None

    async def get_repo_profile(self, repo_profile_id: str) -> RepoProfileRecord | None:
        if repo_profile_id == self.repo_profile.id:
            return self.repo_profile
        return None

    async def list_repo_profile_secret_refs(self, repo_profile_id: str):
        _ = repo_profile_id
        return [binding.secret_ref for binding in self.secret_bindings]

    async def list_repo_profile_secret_bindings(self, repo_profile_id: str):
        _ = repo_profile_id
        return self.secret_bindings


class StubAsyncJobRepository:
    def __init__(self) -> None:
        self.created_jobs: list[AsyncJobRecord] = []

    async def create_job(self, *, job_type: AsyncJobType, payload: dict[str, object], dedupe_key: str):
        now = datetime.now(UTC)
        job = AsyncJobRecord(
            id=f"job-{len(self.created_jobs) + 1}",
            job_type=job_type,
            status=AsyncJobStatus.QUEUED,
            dedupe_key=dedupe_key,
            payload=payload,
            attempts=1,
            available_at=now,
            lease_expires_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.created_jobs.append(job)
        return job


class StubArtifactRepository:
    async def create_artifact(self, **kwargs):
        return SimpleNamespace(id=f"artifact-{kwargs['sandbox_run_id']}")


class StubPatchGenerationService:
    def __init__(self, patch_run: PatchRunRecord) -> None:
        self.patch_run = patch_run
        self.calls: list[tuple[str, bool, int]] = []

    async def get_or_generate_patch(
        self,
        incident_id: str,
        *,
        refresh: bool = False,
        event_limit: int = 50,
    ) -> PatchRunRecord:
        self.calls.append((incident_id, refresh, event_limit))
        return self.patch_run


class StubPatchRepository:
    def __init__(self, patch_runs: list[PatchRunRecord]) -> None:
        self.patch_runs = {patch_run.id: patch_run for patch_run in patch_runs}

    async def get_patch_run(self, patch_run_id: str) -> PatchRunRecord | None:
        return self.patch_runs.get(patch_run_id)


class StubArtifactStorage:
    bucket_name = "test-bucket"

    def put_text(self, *, object_key: str, content: str, content_type: str):
        _ = content_type
        return (f"s3://{self.bucket_name}/{object_key}", len(content), "checksum")


class StubSecretsReader:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get_secret(self, *, external_ref: str) -> str:
        return self.values[external_ref]


class StubLocalRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        *,
        repository_root,
        patch_diff,
        commands,
        incident_id,
        patch_run_id,
        baseline_ref=None,
        secret_env=None,
        secret_files=None,
        secret_bindings=None,
        secrets_reader=None,
    ):
        self.calls.append(
            {
                "repository_root": repository_root,
                "patch_diff": patch_diff,
                "commands": commands,
                "incident_id": incident_id,
                "patch_run_id": patch_run_id,
                "baseline_ref": baseline_ref,
                "secret_env": secret_env or {},
                "secret_files": secret_files or {},
                "secret_bindings": secret_bindings or [],
                "secrets_reader": secrets_reader,
            }
        )
        return SimpleNamespace(
            reproduction_succeeded=True,
            patch_applied=True,
            verification_succeeded=True,
            summary="Sandbox verified the candidate fix.",
            execution_log="sandbox log",
        )


class StubKubernetesMonitor:
    def __init__(
        self,
        *,
        status: str,
        summary: str,
        execution_log: str = "",
        reproduction_succeeded: bool = False,
        patch_applied: bool = False,
        verification_succeeded: bool = False,
    ) -> None:
        self._result = KubernetesJobStatus(
            status=status,
            summary=summary,
            execution_log=execution_log,
            reproduction_succeeded=reproduction_succeeded,
            patch_applied=patch_applied,
            verification_succeeded=verification_succeeded,
        )
        self.calls: list[str] = []

    def poll_status(self, *, external_job_id: str) -> KubernetesJobStatus:
        self.calls.append(external_job_id)
        return self._result


def _build_incident() -> IncidentRecord:
    now = datetime.now(UTC)
    return IncidentRecord(
        id="incident-1",
        project_id="project-1",
        fingerprint="fingerprint-1",
        service="billing-api",
        environment=Environment.PRODUCTION,
        title="Billing timeout",
        status=IncidentStatus.OPEN,
        severity=IncidentSeverity.HIGH,
        first_seen_at=now,
        last_seen_at=now,
        event_count=3,
        latest_telemetry_id="telemetry-1",
        created_at=now,
        updated_at=now,
    )


def _build_repo_profile() -> RepoProfileRecord:
    now = datetime.now(UTC)
    return RepoProfileRecord(
        id="profile-1",
        project_id="project-1",
        provider_repository_id="provider-repo-1",
        runtime_kind=RuntimeKind.PYTHON,
        base_image=None,
        install_command="pip install -r requirements.txt",
        startup_commands=[],
        reproduce_command="pytest tests/test_billing.py::test_timeout",
        verify_command="pytest tests/test_billing.py::test_timeout_fixed",
        success_criteria=None,
        network_allowlist=[],
        active=True,
        created_at=now,
        updated_at=now,
    )


def _build_patch_run(*, patch_run_id: str, diff_text: str) -> PatchRunRecord:
    now = datetime.now(UTC)
    return PatchRunRecord(
        id=patch_run_id,
        incident_id="incident-1",
        repo_profile_id="profile-1",
        status=PatchRunStatus.GENERATED,
        patch_summary="Patch summary",
        rationale="Patch rationale",
        target_files=[],
        unified_diff=diff_text,
        verification_steps=["Run billing test"],
        confidence=0.9,
        model_name="test-model",
        based_on_commit_sha="abc123",
        diff_line_count=2,
        file_count=1,
        created_at=now,
        updated_at=now,
    )


def _build_service(
    *,
    explicit_patch_run: PatchRunRecord,
    generated_patch_run: PatchRunRecord,
    local_runner: StubLocalRunner,
    kubernetes_monitor: StubKubernetesMonitor | None = None,
    secret_refs: list[SecretRefRecord] | None = None,
    secret_bindings: list[RepoProfileSecretBindingRecord] | None = None,
    secrets_reader: StubSecretsReader | None = None,
) -> tuple[
    SandboxVerificationService,
    StubAsyncJobRepository,
    StubPatchGenerationService,
    StubSandboxRepository,
]:
    incident = _build_incident()
    repo_profile = _build_repo_profile()
    async_job_repository = StubAsyncJobRepository()
    patch_generation = StubPatchGenerationService(generated_patch_run)
    sandbox_repository = StubSandboxRepository()
    service = SandboxVerificationService(
        StubIncidentRepository(incident),
        sandbox_repository,
        control_plane_repository=StubControlPlaneRepository(
            repo_profile,
            secret_refs=secret_refs,
            secret_bindings=secret_bindings,
        ),
        async_job_repository=async_job_repository,
        artifact_repository=StubArtifactRepository(),
        patch_repository=StubPatchRepository([explicit_patch_run, generated_patch_run]),
        patch_generation=patch_generation,
        local_runner=local_runner,
        kubernetes_monitor=kubernetes_monitor,
        artifact_storage=StubArtifactStorage(),
        provider_integration_service=SimpleNamespace(),
        secrets_reader=secrets_reader,
    )
    return service, async_job_repository, patch_generation, sandbox_repository


async def test_queue_sandbox_run_uses_explicit_patch_run_id(monkeypatch) -> None:
    monkeypatch.setattr("services.sandbox_verification.get_sandbox_execution_backend", lambda: "local")

    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n",
    )
    local_runner = StubLocalRunner()
    service, _async_jobs, patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=local_runner,
    )

    sandbox_run, job = await service.queue_sandbox_run(
        "incident-1",
        event_limit=25,
        refresh_patch=False,
        patch_run_id=explicit_patch_run.id,
    )

    assert sandbox_run.patch_run_id == explicit_patch_run.id
    assert job.payload["patch_run_id"] == explicit_patch_run.id
    assert job.payload["baseline_commit_sha"] == explicit_patch_run.based_on_commit_sha
    assert patch_generation.calls == []


async def test_process_async_job_uses_explicit_patch_run_from_job_payload(monkeypatch) -> None:
    monkeypatch.setattr("services.sandbox_verification.get_sandbox_execution_backend", lambda: "local")

    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n+VALUE = 'autonomous'\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n+VALUE = 'generated'\n",
    )
    local_runner = StubLocalRunner()
    service, _async_jobs, patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=local_runner,
    )

    _sandbox_run, job = await service.queue_sandbox_run(
        "incident-1",
        event_limit=10,
        refresh_patch=False,
        patch_run_id=explicit_patch_run.id,
    )
    processed_run = await service.process_async_job(job)

    assert processed_run.patch_run_id == explicit_patch_run.id
    assert processed_run.status is SandboxRunStatus.SUCCEEDED
    assert local_runner.calls[0]["patch_diff"] == explicit_patch_run.unified_diff
    assert local_runner.calls[0]["baseline_ref"] == explicit_patch_run.based_on_commit_sha
    assert patch_generation.calls == []


async def test_poll_kubernetes_runs_updates_terminal_result() -> None:
    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n",
    )
    local_runner = StubLocalRunner()
    kubernetes_monitor = StubKubernetesMonitor(
        status="succeeded",
        summary="Kubernetes verification completed successfully.",
        execution_log=(
            "STIMPACT_PHASE_RESULT phase=reproduce status=observed exit_code=1\n"
            "STIMPACT_PHASE_RESULT phase=patch-apply status=passed\n"
            "STIMPACT_PHASE_RESULT phase=verify status=passed\n"
            "pod logs"
        ),
        reproduction_succeeded=True,
        patch_applied=True,
        verification_succeeded=True,
    )
    service, _async_jobs, _patch_generation, sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=local_runner,
        kubernetes_monitor=kubernetes_monitor,
    )

    run = await sandbox_repository.create_sandbox_run(
        incident_id="incident-1",
        patch_run_id="patch-autonomous",
        repo_profile_id="profile-1",
        async_job_id="job-1",
        status=SandboxRunStatus.RUNNING,
        executor_backend="kubernetes",
        external_job_id="stimpact-sandbox-1",
        install_command="pip install -r requirements.txt",
        reproduce_command="pytest tests/test_billing.py::test_timeout",
        verify_command="pytest tests/test_billing.py::test_timeout_fixed",
        reproduction_succeeded=False,
        patch_applied=False,
        verification_succeeded=False,
        summary="Waiting for Kubernetes completion.",
        execution_log="",
    )

    updated_runs = await service.poll_kubernetes_runs(limit=10)

    assert kubernetes_monitor.calls == ["stimpact-sandbox-1"]
    assert len(updated_runs) == 1
    assert updated_runs[0].id == run.id
    assert updated_runs[0].status is SandboxRunStatus.SUCCEEDED
    assert updated_runs[0].reproduction_succeeded is True
    assert updated_runs[0].patch_applied is True
    assert updated_runs[0].verification_succeeded is True


async def test_process_async_job_resolves_repo_profile_secrets_for_local_runner(monkeypatch) -> None:
    monkeypatch.setattr("services.sandbox_verification.get_sandbox_execution_backend", lambda: "local")

    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n+VALUE = 'autonomous'\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n+VALUE = 'generated'\n",
    )
    secret_ref = SecretRefRecord(
        id="secret-1",
        project_id="project-1",
        label="OPENAI_API_KEY",
        description="OpenAI key",
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        external_ref="arn:aws:secretsmanager:us-west-2:123:secret:openai",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    local_runner = StubLocalRunner()
    service, _async_jobs, _patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=local_runner,
        secret_refs=[secret_ref],
        secrets_reader=StubSecretsReader({secret_ref.external_ref: "super-secret-value"}),
    )

    _sandbox_run, job = await service.queue_sandbox_run(
        "incident-1",
        event_limit=10,
        refresh_patch=False,
        patch_run_id=explicit_patch_run.id,
    )
    await service.process_async_job(job)

    assert local_runner.calls[0]["secret_env"] == {}
    assert local_runner.calls[0]["secret_files"] == {}
    assert local_runner.calls[0]["secret_bindings"] == [
        SecretBindingRef(
            mount_as="OPENAI_API_KEY",
            external_ref="arn:aws:secretsmanager:us-west-2:123:secret:openai",
        )
    ]
    assert local_runner.calls[0]["secrets_reader"] is not None


async def test_process_async_job_materializes_relative_secret_file_mounts(monkeypatch) -> None:
    monkeypatch.setattr("services.sandbox_verification.get_sandbox_execution_backend", lambda: "local")

    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n+VALUE = 'autonomous'\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n+VALUE = 'generated'\n",
    )
    secret_ref = SecretRefRecord(
        id="secret-1",
        project_id="project-1",
        label="OPENAI_API_KEY",
        description="OpenAI key",
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        external_ref="arn:aws:secretsmanager:us-west-2:123:secret:openai",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    secret_binding = RepoProfileSecretBindingRecord(
        repo_profile_id="profile-1",
        mount_as=".stimpact/secrets/openai.key",
        secret_ref=secret_ref,
        created_at=secret_ref.created_at,
    )
    local_runner = StubLocalRunner()
    service, _async_jobs, _patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=local_runner,
        secret_refs=[secret_ref],
        secret_bindings=[secret_binding],
        secrets_reader=StubSecretsReader({secret_ref.external_ref: "super-secret-value"}),
    )

    _sandbox_run, job = await service.queue_sandbox_run(
        "incident-1",
        event_limit=10,
        refresh_patch=False,
        patch_run_id=explicit_patch_run.id,
    )
    await service.process_async_job(job)

    assert local_runner.calls[0]["secret_env"] == {}
    assert local_runner.calls[0]["secret_files"] == {}
    assert local_runner.calls[0]["secret_bindings"] == [
        SecretBindingRef(
            mount_as=".stimpact/secrets/openai.key",
            external_ref="arn:aws:secretsmanager:us-west-2:123:secret:openai",
        )
    ]


def test_redact_manifest_masks_secret_references() -> None:
    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n+VALUE = 'autonomous'\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n+VALUE = 'generated'\n",
    )
    service, _async_jobs, _patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=StubLocalRunner(),
    )
    manifest = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "sandbox",
                            "env": [
                                {
                                    "name": "STIMPACT_SECRET_BINDING_0_EXTERNAL_REF",
                                    "value": "arn:aws:secretsmanager:us-west-2:123:secret:openai",
                                },
                                {"name": "SAFE_VALUE", "value": "ok"},
                            ],
                        }
                    ]
                }
            }
        }
    }

    rendered = service._redact_manifest(  # noqa: SLF001
        manifest,
        secret_bindings=[
            RepoProfileSecretBindingRecord(
                repo_profile_id="profile-1",
                mount_as="OPENAI_API_KEY",
                secret_ref=SecretRefRecord(
                    id="secret-1",
                    project_id="project-1",
                    label="OPENAI_API_KEY",
                    description="OpenAI key",
                    backend=SecretBackend.AWS_SECRETS_MANAGER,
                    external_ref="arn:aws:secretsmanager:us-west-2:123:secret:openai",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
                created_at=datetime.now(UTC),
            )
        ],
    )

    assert "***REDACTED***" in rendered
    assert "arn:aws:secretsmanager:us-west-2:123:secret:openai" not in rendered
    assert "SAFE_VALUE" in rendered


def test_resolve_network_allowlist_cidrs_keeps_cidr_entries() -> None:
    explicit_patch_run = _build_patch_run(
        patch_run_id="patch-autonomous",
        diff_text="diff --git a/app.py b/app.py\n+VALUE = 'autonomous'\n",
    )
    generated_patch_run = _build_patch_run(
        patch_run_id="patch-generated",
        diff_text="diff --git a/other.py b/other.py\n+VALUE = 'generated'\n",
    )
    service, _async_jobs, _patch_generation, _sandbox_repository = _build_service(
        explicit_patch_run=explicit_patch_run,
        generated_patch_run=generated_patch_run,
        local_runner=StubLocalRunner(),
    )

    resolved = service._resolve_network_allowlist_cidrs(["10.0.0.0/24", "192.168.10.5"])  # noqa: SLF001

    assert resolved == ["10.0.0.0/24", "192.168.10.5/32"]

from __future__ import annotations

import argparse
import asyncio
import json

from api.db.postgres import PostgresConnectionManager
from api.repositories.control_plane_repository import ControlPlaneRepository
from models.control_plane import ProviderKind, RuntimeKind
from services.aws_secrets_manager import AwsSecretsManagerReader, AwsSecretsManagerWriter
from services.github_provider import GitHubProviderClient
from services.provider_integration_service import ProviderIntegrationService


async def main_async(args: argparse.Namespace) -> None:
    manager = PostgresConnectionManager()
    await manager.connect()
    try:
        repository = ControlPlaneRepository(manager.pool)
        provider_service = ProviderIntegrationService(
            repository,
            secrets_writer=AwsSecretsManagerWriter(),
            secrets_reader=AwsSecretsManagerReader(),
        )

        integration = await repository.find_provider_integration_by_metadata(
            provider=ProviderKind.GITHUB,
            metadata_key="project_id",
            metadata_value=args.project_id,
        )
        if integration is None:
            integration, installation = await provider_service.create_github_app_integration(
                project_id=args.project_id,
                name=f"{args.project_id}-github",
            )
        else:
            installation = await GitHubProviderClient().verify_integration(integration)

        _integration, repositories = await provider_service.sync_repositories(integration.id)
        target = next(
            (
                repo
                for repo in repositories
                if repo.owner.lower() == args.repo_owner.lower() and repo.name.lower() == args.repo_name.lower()
            ),
            None,
        )
        if target is None:
            raise SystemExit(f"Repository {args.repo_owner}/{args.repo_name} was not visible to the GitHub app.")

        provider_repository = await repository.upsert_provider_repository(
            provider_integration_id=integration.id,
            provider=ProviderKind.GITHUB,
            external_repository_id=target.external_repository_id,
            owner=target.owner,
            name=target.name,
            default_branch=args.default_branch,
            clone_url=target.clone_url,
        )
        repo_profile = await repository.create_repo_profile(
            project_id=args.project_id,
            provider_repository_id=provider_repository.id,
            runtime_kind=RuntimeKind.PYTHON,
            base_image=args.base_image,
            install_command=args.install_command,
            startup_commands=[],
            reproduce_command=args.reproduce_command,
            verify_command=args.verify_command,
            success_criteria="Fixture test passes in EKS after the autonomous patch is applied.",
            network_allowlist=args.network_allowlist,
            active=True,
        )
        print(
            json.dumps(
                {
                    "integration_id": integration.id,
                    "installation_account": installation.account_login,
                    "provider_repository_id": provider_repository.id,
                    "provider_repository_default_branch": provider_repository.default_branch,
                    "repo_profile_id": repo_profile.id,
                },
                indent=2,
            )
        )
    finally:
        await manager.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap staging control-plane records for a drill.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--repo-owner", required=True)
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--base-image", default="public.ecr.aws/docker/library/python:3.12")
    parser.add_argument("--install-command", required=True)
    parser.add_argument("--reproduce-command", required=True)
    parser.add_argument("--verify-command", required=True)
    parser.add_argument(
        "--network-allowlist",
        nargs="+",
        default=["github.com", "pypi.org", "files.pythonhosted.org"],
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

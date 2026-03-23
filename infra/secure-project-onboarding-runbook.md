# Secure Project Onboarding Runbook

This runbook validates the secure project onboarding flow in staging from project bootstrap through sandbox verification.

## Preconditions

- `AGENT_PLATFORM_API_URL` points at the staging API.
- `AGENT_PLATFORM_ADMIN_TOKEN` is configured for operator access, or a project API key exists for the target project.
- AWS credentials for the staging cluster can read the Secrets Manager namespace used by the platform.
- GitHub App or GitLab OAuth credentials are configured for staging.
- The staging sandbox service account is wired for AWS Secrets Manager access.

## 1. Bootstrap Project Context

1. Open the UI at `/onboarding`.
2. Enter the target `project_id`.
3. Optionally provide a project-scoped onboarding key to validate project-only access.
4. Select `Bootstrap`.
5. Confirm the onboarding state loads and the suggested next steps render.

## 2. Connect Provider

1. Choose either GitHub App or GitLab OAuth.
2. For GitHub, submit the integration name and installation id.
3. For GitLab, start the OAuth flow and complete the authorization in the provider window.
4. Refresh the onboarding state.
5. Confirm the integration appears under the project and is bound to the expected project id.

## 3. Sync Repositories

1. Use `Sync repos` for the connected integration.
2. Confirm the expected repositories are listed.
3. Select the repository that should back sandbox verification.

## 4. Store Runtime Secrets

1. Add a runtime secret such as `OPENAI_API_KEY` through the onboarding UI.
2. Confirm the secret appears in the UI as an AWS-backed secret ref.
3. Verify in Postgres that only metadata and the external AWS reference are stored.
4. Verify in AWS Secrets Manager that the secret value exists and matches the intended staging secret.

## 5. Create Repo Profile

1. Define the runtime kind, base image, install command, reproduce command, and verify command.
2. Attach at least one secret mount using either an environment variable name or a file path.
3. Create the repo profile.
4. Confirm the repo profile appears in the onboarding state with the expected mount metadata.

## 6. Run Sandbox Verification

1. Trigger a sandbox verification for an incident tied to the newly onboarded project.
2. Confirm the sandbox run reaches the cluster and progresses through reproduce, patch apply, and verify phases.
3. Inspect the stored Kubernetes manifest artifact and confirm it contains only secret references, not plaintext secret values.
4. Confirm the pod fetches secrets from AWS at runtime and that secrets are not present in logs or stored artifacts.

## 7. Post-Validation Checks

- Confirm `provider_access_secret_arn` and repo profile secret refs are present, but plaintext secret values are absent, in stored manifests.
- Confirm sandbox logs redact any retrieved secret values if commands print them accidentally.
- Confirm repo profile secret file mounts are materialized only inside the sandbox workspace or mounted volume.
- Confirm project-scoped onboarding access works with a valid project API key and rejects keys from other projects.

## Exit Criteria

- The project can be bootstrapped from the onboarding UI.
- A Git provider can be connected and repositories synced.
- Runtime secrets are stored in AWS Secrets Manager and surfaced only as metadata in the control plane.
- A repo profile can be created with a secret mount.
- A sandbox run can consume the secret-backed configuration without leaking secrets into manifests, logs, or artifacts.

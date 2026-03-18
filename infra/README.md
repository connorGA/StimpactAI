# Infrastructure Bootstrap

This directory contains the production-scale AWS and Kubernetes bootstrap assets for sandbox execution.

## Step 1. Kubernetes Cluster Strategy

The EKS cluster is split into two namespaces:

- `control-plane` for the FastAPI API, dispatchers, and webhook handlers
- `sandbox` for ephemeral repair, reproduce, and verification jobs

The cluster config also splits node groups by workload:

- `control-plane-ng`: `t3.large`, autoscaling `1-3`
- `sandbox-ng`: `m6i.large`, autoscaling `1-10`

Sandbox nodes are labeled and tainted so sandbox jobs stay isolated from platform services.

## Step 2. Artifact Storage

Create one S3 bucket for platform artifacts. Recommended layout:

- `projects/{project_id}/...`
- `incidents/{incident_id}/...`
- `sandbox_runs/{run_id}/...`
- `telemetry/...`

The backend stores object references in Postgres and writes the artifact bodies to S3.

## Step 3. IAM Roles

Two distinct IAM policies are provided:

- `aws/iam/control-plane-policy.json`
- `aws/iam/sandbox-job-policy.json`

Attach them to separate IAM roles and bind them to Kubernetes service accounts using IRSA:

- `stimpact-control-plane` in namespace `control-plane`
- `stimpact-sandbox-job` in namespace `sandbox`

The sandbox policy is intentionally read-only for Secrets Manager.
The checked-in `kubernetes/namespaces-and-serviceaccounts.yaml` file is a reference template only. For a real cluster, create the IAM-backed service accounts after the policies exist so the role ARNs are correct.

## Step 4. Create The EKS Cluster

Prerequisites:

```sh
brew install kubectl
brew install eksctl
eksctl version
kubectl version --client
```

Cluster config:

- `eks/cluster.yaml`

Create the cluster:

```sh
eksctl create cluster -f infra/eks/cluster.yaml
kubectl get nodes
kubectl apply -f infra/kubernetes/namespaces.yaml
```

## Step 5. Create The S3 Bucket

Use the helper script or run the commands directly:

```sh
./infra/scripts/create_s3_bucket.sh stimpactai-artifacts-dev us-west-2
```

That script creates the bucket and enables versioning.

## Step 6. Secrets Manager Structure

Secrets follow this structure:

```text
stimpactai/projects/{project_id}/env/{env}/{secret_name}
```

Example:

```text
stimpactai/projects/123/env/dev/OPENAI_API_KEY
```

The backend now uses this naming convention when writing secrets to AWS Secrets Manager.

## Step 7. Git Provider Integrations

Development should expose a public base URL through `AGENT_PLATFORM_PUBLIC_BASE_URL`. With ngrok, the provider callback endpoints are:

- GitHub callback: `/api/github/callback`
- GitHub webhook: `/webhooks/github`
- GitLab OAuth callback: `/auth/gitlab/callback`

Current auth model:

- GitHub uses a GitHub App installation flow with app credentials supplied via environment variables.
- GitLab uses an OAuth application flow with `api`, `read_repository`, and `write_repository` scopes.

Required environment variables for provider bootstrap:

- `AGENT_PLATFORM_PUBLIC_BASE_URL`
- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITLAB_APPLICATION_ID`
- `GITLAB_APP_SECRET`
- optionally `GITLAB_BASE_URL` for non-`gitlab.com` installs

The backend now exposes provider onboarding and sync routes:

- `POST /control-plane/provider-integrations/github-app`
- `POST /control-plane/provider-integrations/gitlab/oauth/start`
- `POST /control-plane/provider-integrations/{integration_id}/repositories/sync`
- `GET /control-plane/provider-integrations/{integration_id}/repositories`

GitLab OAuth access and refresh tokens are stored in AWS Secrets Manager through the existing secret-ref control-plane flow. Kubernetes sandbox jobs receive only an AWS secret reference for provider access, not raw tokens in the job manifest.

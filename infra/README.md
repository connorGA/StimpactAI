# Infrastructure Bootstrap

This directory contains the AWS and Kubernetes bootstrap assets for sandbox execution.

## Cost Warning

EKS incurs hourly charges even when nobody is using the product. A cluster that sits idle for days still
accrues:

- EKS control-plane cluster-hours
- additional EKS support charges when the Kubernetes version falls into extended support
- EC2 instance-hours for managed node groups
- EBS, load balancer, NAT gateway, and CloudWatch log charges

Treat this cluster as long-lived infrastructure, not as an ephemeral local-dev environment. If you create
it for testing, make teardown part of the same work session.

## Step 1. Kubernetes Cluster Strategy

The EKS cluster is split into two namespaces:

- `control-plane` for the FastAPI API, dispatchers, and webhook handlers
- `sandbox` for ephemeral repair, reproduce, and verification jobs

The cluster config also splits node groups by workload:

- `control-plane-ng`: `t3.medium`, autoscaling `1-2`
- `sandbox-ng`: `t3.large`, autoscaling `0-4`

Sandbox nodes are labeled and tainted so sandbox jobs stay isolated from platform services.
The checked-in config is now intentionally safer for non-production use:

- Kubernetes `1.35` to stay on standard support by default
- one smaller always-on control-plane node
- zero default sandbox nodes until jobs actually need capacity
- reduced control-plane log types to lower CloudWatch ingestion cost

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

## Step 3.5. Deployable Workloads

The repository now includes first-class production workload manifests under `infra/kubernetes/apps/`:

- `control-plane-config.yaml`
- `database-migration-job.yaml`
- `api-deployment.yaml`
- `frontend-deployment.yaml`
- `worker-deployments.yaml`
- `ingress.yaml`

Recommended rollout order:

1. Apply `namespaces-and-serviceaccounts.yaml`
2. Apply `control-plane-config.yaml`
3. Run `database-migration-job.yaml`
4. Apply `api-deployment.yaml`, `frontend-deployment.yaml`, and `worker-deployments.yaml`
5. Apply `ingress.yaml`

Before applying them, replace the `CHANGE_ME_*` placeholders for image URIs, ACM certificate ARN, artifact bucket, and secrets.

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

Before creating the cluster:

```sh
aws eks describe-cluster-versions --region us-west-2 \
  --query 'clusterVersions[].{version:clusterVersion,status:status,default:defaultVersion}' \
  --output table
```

Choose a version that is still in `STANDARD_SUPPORT` for any long-lived environment.

Create the cluster:

```sh
STIMPACT_ACK_EKS_COSTS=1 ./infra/scripts/create_eks_cluster.sh
```

The helper script now prints a cost warning and requires explicit acknowledgement so it is harder to
accidentally spin up an always-on cluster.

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

## Step 8. Runtime Expectations

Production services now assume:

- `DATABASE_URL` is required
- `REDIS_URL` is required
- readiness should fail when persistence is unavailable
- long-running API and worker services run with `AGENT_PLATFORM_RUN_MIGRATIONS=false`
- database migrations run through the dedicated Kubernetes job rather than API startup

## Step 9. Audit Live Cost Drivers

Use these commands to confirm whether a cluster is still running and whether it has drifted into extended
support:

```sh
aws eks list-clusters --region us-west-2
aws eks describe-cluster --region us-west-2 --name stimpactai-cluster
aws eks list-nodegroups --region us-west-2 --cluster-name stimpactai-cluster
aws eks describe-nodegroup --region us-west-2 --cluster-name stimpactai-cluster --nodegroup-name control-plane-ng
aws eks describe-nodegroup --region us-west-2 --cluster-name stimpactai-cluster --nodegroup-name sandbox-ng
```

Pay special attention to:

- `cluster.version`
- `cluster.upgradePolicy.supportType`
- `nodegroup.scalingConfig`
- any additional CloudWatch, ELB, EBS, or NAT resources that remain after testing

If a dev/test cluster is still present and nobody needs it, deleting it is the fastest way to stop the
majority of the spend.

## Step 10. Tear Down Non-Production Clusters

Delete the cluster:

```sh
STIMPACT_ACK_EKS_DELETE=1 ./infra/scripts/delete_eks_cluster.sh
```

After deletion, manually verify cleanup of any remaining AWS resources that may continue billing:

```sh
aws ec2 describe-volumes --region us-west-2 --filters Name=status,Values=available
aws elbv2 describe-load-balancers --region us-west-2
aws logs describe-log-groups --region us-west-2 --log-group-name-prefix /aws/eks/stimpactai-cluster
```

## Step 11. If The Cluster Must Stay Online

If you cannot delete the cluster yet, reduce cost exposure immediately:

1. Upgrade the cluster to a version that is still in `STANDARD_SUPPORT`.
2. Reduce node-group desired/min capacity, especially for sandbox workers.

Example commands:

```sh
eksctl upgrade cluster --name stimpactai-cluster --region us-west-2 --version 1.35
aws eks update-nodegroup-config \
  --region us-west-2 \
  --cluster-name stimpactai-cluster \
  --nodegroup-name sandbox-ng \
  --scaling-config minSize=0,maxSize=4,desiredSize=0
```

## Recommended Operating Model

- For local development, prefer Docker Compose or other non-EKS workflows whenever possible.
- For short-lived staging or manual validation, create the cluster only for the test window and delete it
  immediately after.
- If a cluster must remain online, keep it on a `STANDARD_SUPPORT` Kubernetes version and scale sandbox
  capacity to zero by default.

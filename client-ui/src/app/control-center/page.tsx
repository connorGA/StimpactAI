import Link from "next/link";

import {
  getCurrentSession,
  getHealthReadiness,
  getProjectPolicy,
  listProjectApiKeys,
  listProviderIntegrations,
  listRepoProfiles,
  listSecretRefs,
  listWorkspaceAccessRequests,
  listWorkspaceInvites,
} from "@/lib/agent-platform";
import { WorkspaceAdminPanel } from "@/components/workspace-admin-panel";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import { PageHeader, ProjectSetupState, SectionCard, StatCard } from "@/components/dashboard-ui";

export const dynamic = "force-dynamic";

const autonomyModes = [
  {
    id: "observe",
    name: "Observe",
    detail: "Analyze incidents only. No repair recommendations or executions are allowed.",
  },
  {
    id: "recommend",
    name: "Recommend",
    detail: "Generate grounded remediation guidance while keeping execution manual.",
  },
  {
    id: "supervised_execute",
    name: "Supervised execute",
    detail: "Allow low-risk execution paths once an operator approves the action.",
  },
  {
    id: "autonomous",
    name: "Autonomous",
    detail: "Permit trusted repair flows to proceed automatically within guardrails.",
  },
] as const;

export default async function ControlCenterPage() {
  const session = await getCurrentSession().catch(() => null);
  const projectId = await resolvePrimaryProjectId();

  if (!session) {
    return (
      <main className="space-y-6">
        <PageHeader
          eyebrow="Control center"
          title="Autonomy policy, guardrails, and agent permissions"
          description="Connect a project, ingest telemetry, or add a repo profile to unlock the control plane."
        />
      </main>
    );
  }

  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Control center"
        title="Create your first project before opening the control center"
        description="The control center needs a project before it can show policy, repo profiles, credentials, and automation guardrails. Start with onboarding, then come back here once your first project is set up."
      />
    );
  }

  const [
    policy,
    integrations,
    repoProfiles,
    apiKeys,
    secretRefs,
    readiness,
    invites,
    accessRequests,
  ] =
    await Promise.all([
      getProjectPolicy(projectId),
      listProviderIntegrations(projectId),
      listRepoProfiles(projectId),
      listProjectApiKeys(projectId),
      listSecretRefs(projectId),
      getHealthReadiness().catch(() => null),
      listWorkspaceInvites(session.organization.id).catch(() => []),
      listWorkspaceAccessRequests(session.organization.id).catch(() => []),
    ]);

  const guardrails = [
    {
      label: "Require human approval",
      enabled: policy.require_human_approval,
      detail: "Human review gates autonomous or production-impacting activity.",
    },
    {
      label: "Block during active deploys",
      enabled: policy.block_during_active_deploys,
      detail: "Prevents repair execution while another rollout is already in progress.",
    },
    {
      label: "Restrict to approved services",
      enabled: policy.restrict_to_approved_services,
      detail:
        policy.approved_services.length > 0
          ? `Approved services: ${policy.approved_services.join(", ")}`
          : "No approved service allowlist is currently defined.",
    },
    {
      label: "Require rollback plan",
      enabled: policy.require_rollback_plan,
      detail: "Patch and execution plans must include a rollback path.",
    },
    {
      label: "Require post-action verification",
      enabled: policy.require_post_action_verification,
      detail: "Verification remains mandatory after a patch or automation run.",
    },
  ];

  const agentConfigs = [
    {
      label: "Failure classifier",
      enabled: policy.failure_classifier_enabled,
      detail: "Categorizes incoming incidents before deeper reasoning begins.",
    },
    {
      label: "Root cause analyzer",
      enabled: policy.root_cause_enabled,
      detail: "Builds grounded RCA from stack traces, code evidence, and incident context.",
    },
    {
      label: "Patch planner",
      enabled: policy.patch_planner_enabled,
      detail: "Drafts candidate fixes and patch summaries for operator review or automation.",
    },
    {
      label: "Runbook executor",
      enabled: policy.runbook_executor_enabled,
      detail: "Controls whether remediation playbooks can execute from the platform.",
    },
  ];

  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Control center"
        title="Autonomy policy, guardrails, and project access"
        description={`Live control-plane state for ${projectId}. Review policy, credentials, repo profiles, and platform readiness here, then use onboarding to connect a new repository or add secrets.`}
        action={
          <Link
            href="/onboarding"
            className="inline-flex rounded-[16px] bg-[#17385d] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1f4a78]"
          >
            Open onboarding
          </Link>
        }
      />

      <section className="grid gap-4 md:grid-cols-4">
        <StatCard
          label="Autonomy mode"
          value={formatMode(policy.autonomy_mode)}
          detail={
            policy.allow_production_writes
              ? "Production writes currently permitted."
              : "Production writes remain blocked."
          }
        />
        <StatCard
          label="Connected repos"
          value={String(repoProfiles.length)}
          detail="Active repo profiles available for sandbox and repair flows."
          tone="blue"
        />
        <StatCard
          label="Project API keys"
          value={String(apiKeys.filter((key) => key.status === "active").length)}
          detail="Active SDK ingest keys currently registered for this project."
          tone="yellow"
        />
        <StatCard
          label="Platform readiness"
          value={readiness?.status ?? "unknown"}
          detail={
            readiness?.checks.database.ready
              ? "Database checks are healthy."
              : "Database readiness needs attention."
          }
          tone="white"
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <SectionCard
          title="Autonomy modes"
          description="The control plane now reflects the persisted project policy."
        >
          <div className="space-y-3">
            {autonomyModes.map((mode) => {
              const active = policy.autonomy_mode === mode.id;
              return (
                <div
                  key={mode.id}
                  className={`rounded-[22px] border px-4 py-4 ${
                    active
                      ? "border-[rgba(255,106,61,0.22)] bg-[rgba(255,106,61,0.08)]"
                      : "border-[rgba(17,24,39,0.08)] bg-white"
                  }`}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="font-semibold text-[#171717]">{mode.name}</p>
                      <p className="mt-1 text-sm leading-6 text-[#746d66]">{mode.detail}</p>
                    </div>
                    <StatusPill active={active} label={active ? "Current" : "Available"} />
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>

        <SectionCard
          title="Project access"
          description="Credentials and repositories currently available to the remediation platform."
        >
          <div className="space-y-4">
            <KeyValueRow label="Provider integrations" value={String(integrations.length)} />
            <KeyValueRow label="Secret refs" value={String(secretRefs.length)} />
            <KeyValueRow
              label="Approved services"
              value={policy.approved_services.length > 0 ? policy.approved_services.join(", ") : "None"}
            />
            <div className="rounded-[20px] bg-[#f8fbff] px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
                Repo profiles
              </p>
              <div className="mt-3 space-y-2 text-sm text-[#35547d]">
                {repoProfiles.map((profile) => (
                  <p key={profile.id}>
                    {profile.runtime_kind} runtime with verify command <code>{profile.verify_command}</code>
                  </p>
                ))}
                {repoProfiles.length === 0 ? <p>No active repo profiles configured.</p> : null}
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard
          title="Guardrails"
          description="Operator safety rules now read from the project policy model."
        >
          <div className="space-y-3">
            {guardrails.map((guardrail) => (
              <div
                key={guardrail.label}
                className="flex items-start justify-between gap-4 rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
              >
                <div>
                  <p className="font-medium text-[#171717]">{guardrail.label}</p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">{guardrail.detail}</p>
                </div>
                <StatusPill active={guardrail.enabled} label={guardrail.enabled ? "Enabled" : "Disabled"} />
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Agent configuration"
          description="Per-agent execution switches currently available for this project."
        >
          <div className="space-y-3">
            {agentConfigs.map((agent) => (
              <div
                key={agent.label}
                className="flex items-start justify-between gap-4 rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
              >
                <div>
                  <p className="font-medium text-[#171717]">{agent.label}</p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">{agent.detail}</p>
                </div>
                <StatusPill active={agent.enabled} label={agent.enabled ? "Enabled" : "Disabled"} />
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {session.role === "owner" || session.role === "admin" ? (
        <SectionCard
          title="Workspace administration"
          description="Invite teammates, review join requests, and keep project-based access within your plan entitlement."
        >
          <WorkspaceAdminPanel
            organizationId={session.organization.id}
            projectCount={session.projects.length}
            includedProjects={session.subscription?.included_projects ?? 1}
            additionalProjectPriceCents={session.subscription?.additional_project_price_cents ?? 0}
            invites={invites}
            accessRequests={accessRequests}
          />
        </SectionCard>
      ) : null}
    </main>
  );
}

function formatMode(mode: string): string {
  return mode
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${
        active
          ? "bg-[rgba(67,160,71,0.12)] text-[#2f6f35]"
          : "bg-[rgba(17,24,39,0.08)] text-[#5f6470]"
      }`}
    >
      {label}
    </span>
  );
}

function KeyValueRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[rgba(17,24,39,0.08)] pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-[#746d66]">{label}</span>
      <span className="text-sm font-semibold text-[#171717]">{value}</span>
    </div>
  );
}

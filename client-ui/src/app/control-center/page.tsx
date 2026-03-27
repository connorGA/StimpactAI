import Link from "next/link";

import {
  getCurrentSession,
  getHealthReadiness,
  getProjectPolicy,
  getProjectOnboarding,
  getProjectServiceSandboxPlan,
  listProjectApiKeys,
  listProjectServices,
  listProviderIntegrations,
  listRepoProfiles,
  listSecretRefs,
  listWorkspaceAccessRequests,
  listWorkspaceInvites,
} from "@/lib/agent-platform";
import { WorkspaceAdminPanel } from "@/components/workspace-admin-panel";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
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
  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Control center"
        title="Finish onboarding before opening the control center"
        description="The control center stays in onboarding-first mode until the current project has a connected provider, synced repositories, stored secrets, and mapped service infrastructure."
      />
    );
  }

  const [
    policy,
    integrations,
    repoProfiles,
    projectServices,
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
      listProjectServices(projectId),
      listProjectApiKeys(projectId),
      listSecretRefs(projectId),
      getHealthReadiness().catch(() => null),
      listWorkspaceInvites(session.organization.id).catch(() => []),
      listWorkspaceAccessRequests(session.organization.id).catch(() => []),
    ]);
  const sandboxPlans = await Promise.all(
    projectServices.map((service) =>
      getProjectServiceSandboxPlan(projectId, service.id).catch(() => null),
    ),
  );

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

      <section className="grid gap-4 md:grid-cols-5">
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
          label="Mapped services"
          value={String(projectServices.length)}
          detail="Named deployable services currently scoped to this project."
          tone="white"
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
          description="Credentials, repositories, and service mappings currently available to the remediation platform."
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
            <div className="rounded-[20px] bg-[#fff7f2] px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
                Project services
              </p>
              <div className="mt-3 space-y-2 text-sm text-[#5f4b41]">
                {projectServices.map((service) => (
                  <p key={service.id}>
                    {service.name} ({service.service_type}) mapped to{" "}
                    <code>
                      {repoProfiles.find((profile) => profile.id === service.repo_profile_id)?.verify_command ??
                        "unmapped profile"}
                    </code>
                  </p>
                ))}
                {projectServices.length === 0 ? <p>No project services configured yet.</p> : null}
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard
          title="Infrastructure map"
          description="A project-scoped view of the repositories, services, and dependencies currently configured."
        >
          <div className="space-y-3">
            {projectServices.length ? (
              projectServices.map((service) => (
                <div
                  key={service.id}
                  className="rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-[#171717]">{service.name}</p>
                    <span className="rounded-full bg-[rgba(255,106,61,0.12)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#d45a2b]">
                      {service.service_type}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[#746d66]">
                    Repo profile:{" "}
                    {repoProfiles.find((profile) => profile.id === service.repo_profile_id)?.verify_command ??
                      "Unmapped"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">
                    Depends on:{" "}
                    {service.dependencies.length
                      ? service.dependencies
                          .map((dependency) => {
                            const match = projectServices.find(
                              (candidate) => candidate.id === dependency.depends_on_service_id,
                            );
                            return match?.name ?? dependency.depends_on_service_id;
                          })
                          .join(" -> ")
                      : "No declared dependencies"}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-[#746d66]">
                No project services have been mapped yet. Use onboarding to define the project
                infrastructure that sandbox verification and autonomous repair should target.
              </p>
            )}
          </div>
        </SectionCard>
        <SectionCard
          title="Sandbox plan preview"
          description="Preview the repo profile, startup commands, and dependency plan the sandbox will use for each mapped service."
        >
          <div className="space-y-3">
            {sandboxPlans.filter(Boolean).length ? (
              sandboxPlans.filter(Boolean).map((plan) => (
                <div
                  key={plan!.target_service.service.id}
                  className="rounded-[20px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
                >
                  <p className="font-medium text-[#171717]">{plan!.target_service.service.name}</p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">
                    Startup:{" "}
                    {plan!.target_service.startup_commands.length
                      ? plan!.target_service.startup_commands.join(" && ")
                      : "No startup commands configured"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">
                    Dependencies:{" "}
                    {plan!.dependency_services.length
                      ? plan!.dependency_services.map((dependency) => dependency.service.name).join(", ")
                      : "None"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[#746d66]">
                    Health checks:{" "}
                    {plan!.target_service.healthcheck_command ||
                      plan!.target_service.healthcheck_url ||
                      "None configured"}
                  </p>
                  {plan!.warnings.length ? (
                    <p className="mt-2 text-sm leading-6 text-[#c25a34]">
                      {plan!.warnings.join(" ")}
                    </p>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-[#746d66]">
                Add at least one mapped service to preview sandbox startup and dependency plans.
              </p>
            )}
          </div>
        </SectionCard>
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

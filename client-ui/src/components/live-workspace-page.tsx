import Link from "next/link";

import { ProjectSetupState } from "@/components/dashboard-ui";
import { LiveManualPingPanel } from "@/components/live-manual-ping-panel";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  getProjectOnboarding,
  getIncidentReportingOverview,
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
} from "@/lib/agent-platform";
import {
  calculateLinePath,
  formatTimestamp,
  getLiveStatusSummary,
  getServiceHealthRows,
} from "@/lib/dashboard";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import type {
  AutonomousRunStatus,
  IncidentAutonomousRunDetail,
  IncidentSummary,
} from "@/lib/types";

export async function LiveWorkspacePage() {
  const projectId = await resolvePrimaryProjectId();
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Live workspace"
        title="Create your first project before opening live operations"
        description="The live workspace reads from project-scoped incident data. Finish onboarding first, then this route will show the active warning stream, current system state, and operator updates."
      />
    );
  }
  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Live workspace"
        title="Finish onboarding before opening live operations"
        description="The live workspace stays in onboarding-first mode until provider connection, repositories, secrets, and service mapping are fully configured for the current project."
      />
    );
  }
  const incidentList = await getIncidents({ projectId: projectId ?? undefined, limit: 12, offset: 0 });
  const reporting = await getIncidentReportingOverview(projectId ?? undefined);
  const incidents = incidentList.items;
  const openIncidents = reporting.open_incidents;
  const liveStatus = getLiveStatusSummary(incidents);
  const serviceHealth = getServiceHealthRows(incidents);
  const incidentTrend = reporting.recent_incident_activity.map((point) => ({
    label: point.label,
    value: point.count,
  }));
  const linePath = calculateLinePath(incidentTrend, 112, 480);
  const autonomousRuns = await loadLatestAutonomousRuns(incidents.slice(0, 6));
  const activeUpdates = buildActiveUpdates(incidents, autonomousRuns);

  return (
    <main className="mx-auto max-w-[1280px] space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between pb-5 pt-1">
        <div>
          <h1 className="text-2xl font-semibold text-[#111827]">Live operations</h1>
          <p className="mt-1 text-sm text-[#6b7280]">
            Real-time system health, active incidents, and service status.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/incidents"
            className="rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-sm font-medium text-[#374151] shadow-sm transition hover:bg-[#f9fafb]"
          >
            Incident history
          </Link>
          <Link
            href="/control-center"
            className="rounded-lg bg-[#111827] px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#1f2937]"
          >
            Control center
          </Link>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-px overflow-hidden rounded-xl border border-[#e5e7eb] bg-[#e5e7eb]">
        <StatCell label="Status" value={openIncidents === 0 ? "Stable" : "Active"} highlight={openIncidents > 0} />
        <StatCell label="Open incidents" value={String(openIncidents)} />
        <StatCell label="Visible incidents" value={String(reporting.total_visible_incidents)} />
        <StatCell label="Event volume" value={String(reporting.total_event_volume)} />
      </div>

      {/* Trend chart */}
      <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-[#111827]">Incident activity</p>
            <p className="mt-0.5 text-xs text-[#9ca3af]">Recent incident pressure over the sampled window</p>
          </div>
          <span className="text-xs text-[#9ca3af]">{liveStatus.title}</span>
        </div>
        <div className="mt-4 rounded-lg bg-[#f9fafb] px-3 py-3">
          <svg viewBox="0 0 480 112" className="h-24 w-full">
            <path
              d={linePath}
              fill="none"
              stroke="#6366f1"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>

      {/* Main content: Incidents + sidebar */}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Incident feed */}
        <div className="rounded-xl border border-[#e5e7eb] bg-white">
          <div className="flex items-center justify-between border-b border-[#f3f4f6] px-5 py-4">
            <p className="text-sm font-semibold text-[#111827]">Active incidents</p>
            <Link
              href="/incidents"
              className="text-xs font-medium text-[#6366f1] hover:text-[#4f46e5]"
            >
              View all →
            </Link>
          </div>

          {incidents.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#f0fdf4]">
                <svg className="h-5 w-5 text-[#22c55e]" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <p className="text-sm font-medium text-[#111827]">All clear</p>
              <p className="mt-1 text-xs text-[#9ca3af]">No active incidents right now.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#f3f4f6]">
              {incidents.slice(0, 6).map((incident) => (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="flex items-center gap-4 px-5 py-3.5 transition hover:bg-[#f9fafb]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={incident.severity} />
                      <StatusBadge status={incident.status} />
                      {autonomousRuns[incident.id] ? (
                        <AutonomousRunBadge status={autonomousRuns[incident.id]!.run.status} />
                      ) : null}
                    </div>
                    <p className="mt-1.5 truncate text-sm font-medium text-[#111827]">
                      {incident.title}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-[#9ca3af]">
                      {incident.service} · {incident.environment} · {formatTimestamp(incident.last_seen_at)}
                    </p>
                    {autonomousRuns[incident.id]?.run.status === "failed" &&
                    autonomousRuns[incident.id]?.run.last_error ? (
                      <p className="mt-1 truncate text-xs text-[#ef4444]">
                        {truncateAutonomousError(autonomousRuns[incident.id]?.run.last_error ?? "")}
                      </p>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold tabular-nums text-[#111827]">{incident.event_count}</p>
                    <p className="text-[11px] text-[#9ca3af]">events</p>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-5">
          {/* Warning stream */}
          <div className="rounded-xl border border-[#e5e7eb] bg-white">
            <div className="flex items-center justify-between border-b border-[#f3f4f6] px-4 py-3">
              <p className="text-sm font-semibold text-[#111827]">Activity feed</p>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${openIncidents === 0 ? "bg-[#f0fdf4] text-[#16a34a]" : "bg-[#fef3c7] text-[#d97706]"}`}>
                {openIncidents === 0 ? "Quiet" : "Active"}
              </span>
            </div>
            <div className="divide-y divide-[#f3f4f6]">
              {activeUpdates.map((update, i) => (
                <div key={`${update.title}-${i}`} className="px-4 py-3">
                  <p className="text-sm font-medium text-[#111827]">{update.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-[#6b7280]">{update.detail}</p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className="text-[11px] text-[#9ca3af]">{update.timestamp}</span>
                    {update.autonomousLabel ? (
                      <span className="rounded bg-[#fef2f2] px-1.5 py-0.5 text-[10px] font-medium text-[#dc2626]">
                        {update.autonomousLabel}
                      </span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Service health */}
          <div className="rounded-xl border border-[#e5e7eb] bg-white">
            <div className="border-b border-[#f3f4f6] px-4 py-3">
              <p className="text-sm font-semibold text-[#111827]">Service health</p>
            </div>
            {serviceHealth.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-[#9ca3af]">
                Populates as incidents arrive.
              </div>
            ) : (
              <div className="divide-y divide-[#f3f4f6]">
                {serviceHealth.map((service) => (
                  <div key={service.label} className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          service.status === "critical"
                            ? "bg-[#ef4444]"
                            : service.status === "watch"
                              ? "bg-[#f59e0b]"
                              : "bg-[#22c55e]"
                        }`}
                      />
                      <span className="text-sm text-[#374151]">{service.label}</span>
                    </div>
                    <span className="text-xs capitalize text-[#9ca3af]">{service.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <LiveManualPingPanel
            projectId={projectId}
            services={onboarding.project_services}
            heartbeats={onboarding.telemetry_heartbeats}
          />
        </div>
      </div>
    </main>
  );
}

function StatCell({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-white px-5 py-4">
      <p className="text-xs font-medium text-[#6b7280]">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${highlight ? "text-[#f59e0b]" : "text-[#111827]"}`}>
        {value}
      </p>
    </div>
  );
}

type AutonomousRunLookup = Record<string, IncidentAutonomousRunDetail | null>;

function buildActiveUpdates(
  incidents: IncidentSummary[],
  autonomousRuns: AutonomousRunLookup,
) {
  if (incidents.length === 0) {
    return [
      {
        title: "No active warnings",
        detail: "The platform is not reporting any active incident.",
        timestamp: "Now",
        autonomousLabel: null,
      },
    ];
  }

  return incidents.slice(0, 4).map((incident) => {
    const autonomousRun = autonomousRuns[incident.id];
    return {
      title: incident.title,
      detail: `${incident.service} · ${incident.environment} · ${incident.event_count} events`,
      timestamp: formatTimestamp(incident.last_seen_at),
      autonomousLabel:
        autonomousRun?.run.status === "failed"
          ? "Repair failed"
          : autonomousRun
            ? buildAutonomousLabel(autonomousRun.run.status)
            : null,
    };
  });
}

async function loadLatestAutonomousRuns(
  incidents: IncidentSummary[],
): Promise<AutonomousRunLookup> {
  const pairs = await Promise.all(
    incidents.map(async (incident) => {
      try {
        const detail = await getLatestIncidentAutonomousRunDetail(incident.id);
        return [incident.id, detail] as const;
      } catch {
        return [incident.id, null] as const;
      }
    }),
  );
  return Object.fromEntries(pairs);
}

function buildAutonomousLabel(status: AutonomousRunStatus): string | null {
  if (status === "failed") return "Repair failed";
  if (status === "running" || status === "queued") return "Repairing";
  if (status === "succeeded") return "Repaired";
  return null;
}

function truncateAutonomousError(error: string): string {
  return error.length <= 100 ? error : `${error.slice(0, 97)}…`;
}

function AutonomousRunBadge({ status }: { status: AutonomousRunStatus }) {
  const config: Record<string, { label: string; className: string }> = {
    failed: { label: "Repair failed", className: "bg-[#fef2f2] text-[#dc2626]" },
    running: { label: "Repairing", className: "bg-[#eff6ff] text-[#2563eb]" },
    queued: { label: "Queued", className: "bg-[#eff6ff] text-[#2563eb]" },
    succeeded: { label: "Repaired", className: "bg-[#f0fdf4] text-[#16a34a]" },
    cancelled: { label: "Cancelled", className: "bg-[#f9fafb] text-[#6b7280]" },
  };
  const { label, className } = config[status] ?? config.cancelled!;
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${className}`}>
      {label}
    </span>
  );
}

"use client";

import Link from "next/link";
import { useMemo } from "react";

import { DashboardMetricCard } from "@/components/dashboard-metric-cards";
import { ChatPanel } from "@/components/chat-panel";
import { IncidentHubIdleHero, IncidentLiveControlPanel } from "@/components/incident-live-control-panel";
import { RecentIncidentsList } from "@/components/recent-incidents-list";
import type {
  IncidentAutonomousRunDetail,
  IncidentReportingOverview,
  IncidentSummary,
  SuppressionSummary,
} from "@/lib/types";

type IncidentCommandCenterProps = {
  projectId: string;
  incidents: IncidentSummary[];
  reporting: IncidentReportingOverview;
  autonomousRuns: Record<string, IncidentAutonomousRunDetail | null>;
  suppression?: SuppressionSummary | null;
};

function pickPrimaryOpenIncident(incidents: IncidentSummary[]): IncidentSummary | null {
  const open = incidents.filter((i) => i.status === "open");
  if (open.length === 0) return null;
  return [...open].sort(
    (a, b) => new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime(),
  )[0]!;
}

export function IncidentCommandCenter({
  projectId,
  incidents,
  reporting,
  autonomousRuns,
  suppression,
}: IncidentCommandCenterProps) {
  const primaryOpenIncident = useMemo(() => pickPrimaryOpenIncident(incidents), [incidents]);
  const globalOpen = reporting.open_incidents;
  const hasRepair = incidents.some(
    (i) =>
      i.status === "open" &&
      (autonomousRuns[i.id]?.run.status === "running" || autonomousRuns[i.id]?.run.status === "queued"),
  );

  const chatEndpoint = primaryOpenIncident
    ? `/api/incidents/${primaryOpenIncident.id}/chat`
    : "/api/incidents/chat";
  const chatBody = primaryOpenIncident
    ? { event_limit: 50 }
    : { project_id: projectId, incident_limit: 20 };

  const runDetailForOpen = primaryOpenIncident
    ? autonomousRuns[primaryOpenIncident.id] ?? null
    : null;

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-12 pt-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Incident center</h1>
          {globalOpen > 0 ? (
            <span className="flex items-center gap-1.5 rounded-full border border-[rgba(255,106,61,0.3)] bg-[rgba(255,106,61,0.12)] px-2.5 py-1">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff6a3d] opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#ff6a3d]" />
              </span>
              <span className="text-[11px] font-semibold text-[#ffb99a]">
                {globalOpen} active incident{globalOpen !== 1 ? "s" : ""}
                {hasRepair ? " · repairing" : ""}
              </span>
            </span>
          ) : (
            <span
              role="status"
              aria-label="No open incidents; all healthy"
              className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(32,201,51,0.28)] bg-[rgba(32,201,51,0.1)] px-2.5 py-1"
              title="No open incidents for this project"
            >
              <span className="h-2 w-2 shrink-0 rounded-full bg-[#20c933]" aria-hidden />
              <span className="text-[11px] font-semibold text-[#86efac]">All healthy</span>
            </span>
          )}
        </div>
        <Link
          href="/live"
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.08]"
        >
          Live dashboard
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <DashboardMetricCard
          label="Total incidents"
          hint="Incidents visible for the active project"
          value={String(reporting.total_visible_incidents)}
        />
        <DashboardMetricCard
          label="Open incidents"
          hint="Currently open incidents"
          value={reporting.open_incidents === 0 ? "None" : String(reporting.open_incidents)}
          valueClassName={reporting.open_incidents === 0 ? "text-[#20c933]" : "text-[#ff6a3d]"}
        />
        <DashboardMetricCard
          label="Critical incidents"
          hint="Critical-severity incidents in scope"
          value={reporting.critical_incidents === 0 ? "None" : String(reporting.critical_incidents)}
          valueClassName={reporting.critical_incidents === 0 ? "text-white" : "text-[#ffb253]"}
        />
        <DashboardMetricCard
          label="Agent resolution rate"
          hint="% of resolved incidents attributed to the agent in the last 30d"
          value={
            reporting.agent_resolution_percent_last_30d == null
              ? "—"
              : `${reporting.agent_resolution_percent_last_30d.toFixed(1)}%`
          }
          delta={
            reporting.agent_resolution_delta_pp == null
              ? null
              : {
                  value: reporting.agent_resolution_delta_pp,
                  mode: "higherIsGood",
                  format: "percent",
                }
          }
        />
      </div>

      {suppression ? (
        <Link
          href={`/incidents/noise?project_id=${encodeURIComponent(projectId)}`}
          className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm transition hover:border-white/20 hover:bg-white/[0.05]"
          title="Telemetry the platform filtered out of incident triage in the last 24h"
        >
          <div className="flex items-center gap-3">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-[11px] font-semibold text-white/70">
              {suppression.user_error_event_count + suppression.code_ambiguous_event_count}
            </span>
            <div className="flex flex-col">
              <span className="text-xs font-semibold uppercase tracking-wide text-white/60">
                Suppressed telemetry (24h)
              </span>
              <span className="text-[13px] text-white/80">
                {suppression.user_error_event_count} user-error ·{" "}
                {suppression.code_ambiguous_event_count} needs-review ·{" "}
                {suppression.user_error_unique_fingerprints +
                  suppression.code_ambiguous_unique_fingerprints}{" "}
                unique fingerprints
              </span>
            </div>
          </div>
          <span className="text-[11px] font-medium text-white/60">Review &rarr;</span>
        </Link>
      ) : null}

      {primaryOpenIncident ? (
        <IncidentLiveControlPanel
          incident={primaryOpenIncident}
          initialAutonomousDetail={runDetailForOpen}
        />
      ) : (
        <IncidentHubIdleHero />
      )}

      <div className="grid min-h-0 items-stretch gap-4 lg:grid-cols-2">
        <div className="flex h-full min-h-0 flex-col">
          <ChatPanel
            variant="dark"
            compact
            showAssistantIcon
            showExpandToggle={false}
            showSuggestedPrompts={false}
            title="Assistant"
            description=""
            endpoint={chatEndpoint}
            extraBody={chatBody}
            className="h-full max-h-[calc(100vh-10rem)] min-h-[28rem]"
          />
        </div>

        <div className="flex h-full min-h-0 flex-col">
          <RecentIncidentsList
            className="h-full min-h-0 flex-1"
            incidents={incidents}
            autonomousRuns={autonomousRuns}
          />
        </div>
      </div>
    </main>
  );
}

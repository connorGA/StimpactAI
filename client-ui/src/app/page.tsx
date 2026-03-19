import Link from "next/link";

import { PreviewNotice } from "@/components/dashboard-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
} from "@/lib/agent-platform";
import {
  buildIncidentTrendSeries,
  calculateLinePath,
  calculateUptimePreview,
  countCriticalIncidents,
  countOpenIncidents,
  formatTimestamp,
  getLiveStatusSummary,
  getServiceHealthRows,
} from "@/lib/dashboard";
import type {
  AutonomousRunStatus,
  IncidentAutonomousRunDetail,
  IncidentSummary,
} from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  const incidentList = await getIncidents({ limit: 12, offset: 0 });
  const incidents = incidentList.items;
  const openIncidents = countOpenIncidents(incidents);
  const criticalIncidents = countCriticalIncidents(incidents);
  const uptimePreview = calculateUptimePreview(incidents);
  const liveStatus = getLiveStatusSummary(incidents);
  const serviceHealth = getServiceHealthRows(incidents);
  const incidentTrend = buildIncidentTrendSeries(incidents);
  const linePath = calculateLinePath(incidentTrend, 112, 480);
  const autonomousRuns = await loadLatestAutonomousRuns(incidents.slice(0, 4));
  const activeUpdates = buildActiveUpdates(incidents, autonomousRuns);

  return (
    <main className="space-y-8">
      <section className="px-1">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Live operations
            </p>
            <h1 className="ops-title mt-3 max-w-4xl text-4xl font-semibold tracking-tight lg:text-[3.25rem]">
              Operational status, warning flow, and active service posture
            </h1>
            <p className="ops-copy mt-4 max-w-3xl text-sm leading-7">
              The live page should read like an operations workspace. It is about
              what changed, what is risky, and what needs attention right now.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/incidents"
              className="ops-button-secondary inline-flex rounded-full px-4 py-2.5 text-sm font-semibold"
            >
              Incident history
            </Link>
            <Link
              href="/control-center"
              className="ops-button inline-flex rounded-full px-4 py-2.5 text-sm font-semibold"
            >
              Open controls
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <section className="ops-sheet-dark rounded-[28px] p-7">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/46">
                  Current system state
                </p>
                <h2 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-white">
                  {liveStatus.title}
                </h2>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-white/70">
                  {liveStatus.detail}
                </p>
              </div>
              <span className="ops-pill-strong inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]">
                {openIncidents === 0 ? "Stable" : "Watching"}
              </span>
            </div>

            <div className="grid gap-4 border-y border-white/10 py-5 md:grid-cols-3">
              <LiveMetric label="Current uptime" value={uptimePreview} detail="Preview until SLO telemetry is wired." />
              <LiveMetric label="Open incidents" value={String(openIncidents)} detail="Issues currently requiring investigation." />
              <LiveMetric label="Critical incidents" value={String(criticalIncidents)} detail="Highest-severity items in the queue." />
            </div>

            <div className="rounded-[22px] border border-white/10 bg-white/4 p-4">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/46">
                    Signal shape
                  </p>
                  <p className="mt-2 text-sm text-white/68">
                    Recent incident pressure over the sampled window.
                  </p>
                </div>
                <Link href="/metrics" className="text-sm font-semibold text-white/80 transition hover:text-white">
                  Open metrics
                </Link>
              </div>
              <div className="ops-grid-chart mt-4 rounded-[18px] bg-black/10 px-4 py-4">
                <svg viewBox="0 0 480 112" className="h-28 w-full">
                  <path
                    d={linePath}
                    fill="none"
                    stroke="url(#liveSignalLine)"
                    strokeWidth="4"
                    strokeLinecap="round"
                  />
                  <defs>
                    <linearGradient id="liveSignalLine" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#ffb253" />
                      <stop offset="100%" stopColor="#ff5a2a" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>
          </div>
        </section>

        <aside className="ops-sheet-muted rounded-[28px] p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="ops-kicker text-[11px] font-semibold uppercase">
                Warning stream
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-[#171717]">
                Incoming operator updates
              </h2>
            </div>
            <span className="ops-pill inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]">
              {openIncidents === 0 ? "Quiet" : "Active"}
            </span>
          </div>

          <div className="ops-row-divider mt-6">
            {activeUpdates.map((update) => (
              <div key={`${update.title}-${update.timestamp}`} className="py-4 first:pt-0 last:pb-0">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-[#171717]">{update.title}</p>
                    <p className="mt-1 text-sm leading-6 text-[#5f6470]">{update.detail}</p>
                    {update.autonomousLabel ? (
                      <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#b4453d]">
                        {update.autonomousLabel}
                      </p>
                    ) : null}
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8f735c]">
                    {update.timestamp}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="ops-sheet rounded-[28px] p-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="ops-kicker text-[11px] font-semibold uppercase">
                Live incident feed
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-[#171717]">
                Active warnings and updates
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-[#5f6470]">
                A running feed of the most relevant visible incidents. This is a
                working surface, not a stack of summary cards.
              </p>
            </div>
            <Link
              href="/incidents"
              className="ops-button-secondary inline-flex rounded-full px-4 py-2.5 text-sm font-semibold"
            >
              Open incident center
            </Link>
          </div>

          <div className="mt-6 border-t border-[rgba(24,24,27,0.08)]">
            {incidents.length === 0 ? (
              <div className="py-10 text-sm text-[#5f6470]">
                No live incident warnings are currently present.
              </div>
            ) : (
              incidents.slice(0, 4).map((incident) => (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="block border-b border-[rgba(24,24,27,0.08)] py-5 transition last:border-b-0 hover:bg-white/24"
                >
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityBadge severity={incident.severity} />
                        <StatusBadge status={incident.status} />
                        {autonomousRuns[incident.id] ? (
                          <AutonomousRunBadge
                            status={autonomousRuns[incident.id]!.run.status}
                          />
                        ) : null}
                        <span className="text-xs uppercase tracking-[0.14em] text-[#8f735c]">
                          {incident.service}
                        </span>
                      </div>
                      <h3 className="mt-3 text-lg font-semibold text-[#171717]">
                        {incident.title}
                      </h3>
                      <p className="mt-1 text-sm text-[#5f6470]">
                        {incident.project_id} • {incident.environment} • last update{" "}
                        {formatTimestamp(incident.last_seen_at)}
                      </p>
                      {autonomousRuns[incident.id]?.run.status === "failed" &&
                      autonomousRuns[incident.id]?.run.last_error ? (
                        <p className="mt-2 text-sm text-[#b4453d]">
                          Latest autonomous repair failed:{" "}
                          {truncateAutonomousError(autonomousRuns[incident.id]?.run.last_error ?? "")}
                        </p>
                      ) : null}
                    </div>

                    <div className="grid min-w-[220px] grid-cols-2 gap-6 xl:text-right">
                      <FeedStat label="Events" value={String(incident.event_count)} />
                      <FeedStat
                        label="Telemetry"
                        value={incident.latest_telemetry_id.slice(0, 10)}
                      />
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>

        <aside className="space-y-6">
          <section className="ops-sheet rounded-[28px] p-6">
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Service health
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-[#171717]">
              Health by impacted service
            </h2>

            <div className="ops-row-divider mt-5">
              {serviceHealth.length === 0 ? (
                <div className="py-4 text-sm text-[#5f6470]">
                  Service health will populate as incidents arrive.
                </div>
              ) : (
                serviceHealth.map((service) => (
                  <div
                    key={service.label}
                    className="flex items-center justify-between py-4 first:pt-0 last:pb-0"
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`h-2.5 w-2.5 rounded-full ${
                          service.status === "critical"
                            ? "vault-dot"
                            : service.status === "watch"
                              ? "bg-[linear-gradient(180deg,#ffb84d,#ff8d35)]"
                              : "vault-dot-green"
                        }`}
                      />
                      <span className="text-sm font-medium text-[#171717]">
                        {service.label}
                      </span>
                    </div>
                    <span className="text-sm capitalize text-[#5f6470]">
                      {service.status}
                    </span>
                  </div>
                ))
              )}
            </div>
          </section>

          <PreviewNotice
            title="Still to be wired on the live page"
            items={[
              "True uptime and SLO telemetry will replace the preview uptime metric.",
              "Streaming updates and deploy markers are designed for this page but not live yet.",
            ]}
          />
        </aside>
      </section>
    </main>
  );
}

function LiveMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="border-l border-white/10 pl-4 first:border-l-0 first:pl-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/42">
        {label}
      </p>
      <p className="mt-3 text-4xl font-semibold text-white">{value}</p>
      <p className="mt-2 text-sm leading-6 text-white/62">{detail}</p>
    </div>
  );
}

function FeedStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
        {label}
      </p>
      <p className="mt-2 truncate text-sm font-semibold text-[#171717]">{value}</p>
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
        title: "No active incident updates",
        detail: "The platform is currently not reporting a new active warning.",
        timestamp: "Now",
        autonomousLabel: null,
      },
      {
        title: "Uptime looks stable",
        detail: "Current preview uptime is healthy while no live incidents are visible.",
        timestamp: "Now",
        autonomousLabel: null,
      },
    ];
  }

  return incidents.slice(0, 3).map((incident) => {
    const autonomousRun = autonomousRuns[incident.id];
    if (autonomousRun?.run.status === "failed") {
      return {
        title: incident.title,
        detail: `${incident.service} in ${incident.environment} has ${incident.event_count} attached events. The latest autonomous repair attempt stopped before completion.`,
        timestamp: formatTimestamp(incident.last_seen_at),
        autonomousLabel: "Autonomous repair failed",
      };
    }
    return {
      title: incident.title,
      detail: `${incident.service} in ${incident.environment} has ${incident.event_count} attached events.`,
      timestamp: formatTimestamp(incident.last_seen_at),
      autonomousLabel: autonomousRun ? buildAutonomousLabel(autonomousRun.run.status) : null,
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
  if (status === "failed") {
    return "Autonomous repair failed";
  }
  if (status === "running" || status === "queued") {
    return "Autonomous repair active";
  }
  return null;
}

function truncateAutonomousError(error: string): string {
  return error.length <= 120 ? error : `${error.slice(0, 117)}...`;
}

function AutonomousRunBadge({ status }: { status: AutonomousRunStatus }) {
  const label =
    status === "failed"
      ? "Autonomous failed"
      : status === "running" || status === "queued"
        ? "Autonomous active"
        : status === "succeeded"
          ? "Autonomous succeeded"
          : "Autonomous cancelled";
  const className =
    status === "failed"
      ? "bg-[rgba(233,89,80,0.12)] text-[#b4453d]"
      : status === "running" || status === "queued"
        ? "bg-[rgba(44,123,229,0.12)] text-[#35547d]"
        : status === "succeeded"
          ? "bg-[rgba(67,160,71,0.12)] text-[#2f6f35]"
          : "bg-[rgba(24,24,27,0.08)] text-[#5f6470]";
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${className}`}
    >
      {label}
    </span>
  );
}

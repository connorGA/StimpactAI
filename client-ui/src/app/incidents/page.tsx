import Link from "next/link";

import { ProjectSetupState } from "@/components/dashboard-ui";
import { PaginationControls } from "@/components/pagination-controls";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
} from "@/lib/agent-platform";
import {
  countCriticalIncidents,
  countOpenIncidents,
  formatTimestamp,
} from "@/lib/dashboard";
import { resolvePrimaryProjectId } from "@/lib/project-context";

export const dynamic = "force-dynamic";

type IncidentsPageProps = {
  searchParams: Promise<{
    project_id?: string;
    status?: string;
    page?: string;
    page_size?: string;
  }>;
};

export default async function IncidentsPage({ searchParams }: IncidentsPageProps) {
  const params = await searchParams;
  const projectId = params.project_id?.trim() || (await resolvePrimaryProjectId()) || undefined;
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Incident center"
        title="Create a protected project before browsing incident history"
        description="Incident history is scoped to a protected project. Complete onboarding first, then this route will load the ledger, filters, and response status for that project."
      />
    );
  }
  const status = params.status?.trim() || undefined;
  const pageSize = parsePageSize(params.page_size);
  const requestedPage = parsePage(params.page);

  let incidentList = await getIncidents({
    projectId,
    status,
    limit: pageSize,
    offset: (requestedPage - 1) * pageSize,
  });

  const totalPages = Math.max(1, Math.ceil(incidentList.total / pageSize));
  const currentPage = Math.min(requestedPage, totalPages);

  if (currentPage !== requestedPage) {
    incidentList = await getIncidents({
      projectId,
      status,
      limit: pageSize,
      offset: (currentPage - 1) * pageSize,
    });
  }

  const incidents = incidentList.items;
  const featured = incidents[0];
  const featuredAutonomousRun = featured
    ? await getLatestIncidentAutonomousRunDetail(featured.id).catch(() => null)
    : null;
  const rangeLabel = buildRangeLabel(currentPage, pageSize, incidentList.total);
  const paginationQuery = {
    project_id: projectId,
    status,
  };

  return (
    <main className="space-y-8">
      <section className="px-1">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Incident center
            </p>
            <h1 className="ops-title mt-3 max-w-4xl text-4xl font-semibold tracking-tight lg:text-[3.1rem]">
              Incident history, operator triage, and live response progress
            </h1>
            <p className="ops-copy mt-4 max-w-3xl text-sm leading-7">
              This route leans into case management. The incident list behaves
              like a working ledger and the right rail stays focused on response
              state, not decorative summaries.
            </p>
          </div>

          <div className="ops-sheet-muted grid min-w-[300px] grid-cols-2 gap-4 rounded-[24px] p-5">
            <IncidentStat label="Showing" value={rangeLabel} />
            <IncidentStat label="Total" value={String(incidentList.total)} />
            <IncidentStat label="Open" value={String(countOpenIncidents(incidents))} />
            <IncidentStat label="Critical" value={String(countCriticalIncidents(incidents))} />
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
        <section className="ops-sheet rounded-[28px] p-6">
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Incident history
          </p>

          <form className="mt-5 border-b border-[rgba(24,24,27,0.08)] pb-5">
            <div className="flex flex-col gap-3 xl:flex-row">
              <label className="flex-1">
                <span className="mb-2 block text-sm font-medium text-[#111827]">Project ID</span>
                <input
                  type="text"
                  name="project_id"
                  defaultValue={projectId}
                  placeholder="Filter by project"
                  className="vault-input w-full rounded-[18px] px-3 py-2.5 text-sm text-[#111827]"
                />
              </label>
              <label className="w-full xl:w-[180px]">
                <span className="mb-2 block text-sm font-medium text-[#111827]">Status</span>
                <select
                  name="status"
                  defaultValue={status ?? ""}
                  className="vault-input w-full rounded-[18px] px-3 py-2.5 text-sm text-[#111827]"
                >
                  <option value="">All</option>
                  <option value="open">Open</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
              <label className="w-full xl:w-[180px]">
                <span className="mb-2 block text-sm font-medium text-[#111827]">Page size</span>
                <select
                  name="page_size"
                  defaultValue={String(pageSize)}
                  className="vault-input w-full rounded-[18px] px-3 py-2.5 text-sm text-[#111827]"
                >
                  <option value="10">10 per page</option>
                  <option value="25">25 per page</option>
                  <option value="50">50 per page</option>
                </select>
              </label>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <input type="hidden" name="page" value="1" />
              <button
                type="submit"
                className="ops-button rounded-full px-4 py-2 text-sm font-semibold"
              >
                Apply filters
              </button>
              <Link
                href="/incidents"
                className="ops-button-secondary rounded-full px-4 py-2 text-sm font-semibold"
              >
                Reset
              </Link>
            </div>
          </form>

          <div className="mt-6">
            <PaginationControls
              pathname="/incidents"
              query={paginationQuery}
              currentPage={currentPage}
              pageSize={pageSize}
              totalItems={incidentList.total}
              itemLabel="incidents"
            />
          </div>

          <div className="mt-4">
            {incidents.length === 0 ? (
              <div className="py-10 text-sm text-[#5f6470]">
                No incidents match the current filters.
              </div>
            ) : (
              incidents.map((incident) => (
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
                        <span className="text-xs uppercase tracking-[0.14em] text-[#8f735c]">
                          {incident.environment}
                        </span>
                      </div>
                      <h2 className="mt-3 text-lg font-semibold text-[#111827]">
                        {incident.title}
                      </h2>
                      <p className="mt-1 text-sm text-[#5f6470]">
                        {incident.project_id} • {incident.service} • last seen{" "}
                        {formatTimestamp(incident.last_seen_at)}
                      </p>
                    </div>

                    <div className="grid min-w-[220px] grid-cols-2 gap-6 xl:text-right">
                      <HistoryMetric label="Events" value={String(incident.event_count)} />
                      <HistoryMetric
                        label="Telemetry"
                        value={incident.latest_telemetry_id.slice(0, 10)}
                      />
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>

          {incidents.length > 0 ? (
            <div className="mt-6 border-t border-[rgba(24,24,27,0.08)] pt-6">
              <PaginationControls
                pathname="/incidents"
                query={paginationQuery}
                currentPage={currentPage}
                pageSize={pageSize}
                totalItems={incidentList.total}
                itemLabel="incidents"
              />
            </div>
          ) : null}
        </section>

        <div className="space-y-6">
          <section className="ops-sheet-dark rounded-[28px] p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/48">
                  Active progress
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  {featured ? "Live incident progress" : "Progress feed waiting"}
                </h2>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="ops-pill-strong rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]">
                  {featured ? featured.status : "Idle"}
                </span>
                {featuredAutonomousRun ? (
                  <span
                    className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${
                      featuredAutonomousRun.run.status === "failed"
                        ? "bg-[rgba(233,89,80,0.16)] text-[#ffd5d1]"
                        : featuredAutonomousRun.run.status === "running" ||
                            featuredAutonomousRun.run.status === "queued"
                          ? "bg-[rgba(111,158,210,0.18)] text-white"
                          : "bg-white/10 text-white/78"
                    }`}
                  >
                    {buildAutonomousSummaryLabel(featuredAutonomousRun.run.status)}
                  </span>
                ) : null}
              </div>
            </div>

            {featured ? (
              <div className="mt-6">
                <div className="rounded-[20px] border border-white/10 bg-white/6 px-4 py-4">
                  <p className="font-semibold text-white">{featured.title}</p>
                  <p className="mt-2 text-sm leading-6 text-white/68">
                    {featured.service} • {featured.environment} • fingerprint{" "}
                    {featured.fingerprint.slice(0, 14)}
                  </p>
                  {featuredAutonomousRun?.run.status === "failed" &&
                  featuredAutonomousRun.run.last_error ? (
                    <p className="mt-3 text-sm leading-6 text-[#ffd5d1]">
                      Latest autonomous repair failed:{" "}
                      {truncateAutonomousError(featuredAutonomousRun.run.last_error)}
                    </p>
                  ) : null}
                </div>

                <div className="mt-6 space-y-5">
                  {buildIncidentProgress(featured).map((step, index) => (
                    <div key={step.title} className="flex gap-4">
                      <div className="flex flex-col items-center">
                        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-sm font-semibold text-white">
                          {index + 1}
                        </span>
                        {index < 2 ? <span className="mt-2 h-full w-px bg-white/12" /> : null}
                      </div>
                      <div className="pb-4">
                        <p className="font-medium text-white">{step.title}</p>
                        <p className="mt-1 text-sm leading-6 text-white/70">{step.detail}</p>
                        <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/42">
                          {step.timestamp}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-6 text-sm leading-7 text-white/68">
                When a live incident is present, its current progress updates will
                appear here.
              </div>
            )}
          </section>

          <section className="ops-sheet-muted rounded-[28px] p-6">
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Incident-specific metrics
            </p>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <HistoryMetric label="Tracked incidents" value={String(incidentList.total)} />
              <HistoryMetric
                label="Open incidents"
                value={String(countOpenIncidents(incidents))}
              />
              <HistoryMetric
                label="Critical incidents"
                value={String(countCriticalIncidents(incidents))}
              />
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function parsePage(value?: string): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function parsePageSize(value?: string): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return parsed === 10 || parsed === 25 || parsed === 50 ? parsed : 25;
}

function buildRangeLabel(currentPage: number, pageSize: number, totalItems: number): string {
  if (totalItems === 0) {
    return "0";
  }

  const start = (currentPage - 1) * pageSize + 1;
  const end = Math.min(totalItems, currentPage * pageSize);
  return `${start}-${end}`;
}

function IncidentStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l border-[rgba(24,24,27,0.08)] pl-4 first:border-l-0 first:pl-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
        {label}
      </p>
      <p className="mt-3 text-3xl font-semibold text-[#111827]">{value}</p>
    </div>
  );
}

function HistoryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
        {label}
      </p>
      <p className="mt-2 truncate text-sm font-semibold text-[#111827]">{value}</p>
    </div>
  );
}

function buildIncidentProgress(incident: {
  title: string;
  service: string;
  status: string;
  last_seen_at: string;
  event_count: number;
}) {
  return [
    {
      title: "Incident detected",
      detail: `${incident.service} crossed the current alert threshold and the incident was grouped.`,
      timestamp: formatTimestamp(incident.last_seen_at),
    },
    {
      title: "Operator review in progress",
      detail: `${incident.event_count} linked events are available for the active investigation timeline.`,
      timestamp: "Monitoring",
    },
    {
      title: `Current status: ${incident.status}`,
      detail: "Additional response-state updates and assignee tracking will appear here once wired.",
      timestamp: "Awaiting update",
    },
  ];
}

function buildAutonomousSummaryLabel(status: string): string {
  if (status === "failed") {
    return "Autonomous failed";
  }
  if (status === "running" || status === "queued") {
    return "Autonomous active";
  }
  if (status === "succeeded") {
    return "Autonomous succeeded";
  }
  return "Autonomous cancelled";
}

function truncateAutonomousError(error: string): string {
  return error.length <= 140 ? error : `${error.slice(0, 137)}...`;
}

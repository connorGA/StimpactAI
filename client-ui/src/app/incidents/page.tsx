import Link from "next/link";

import { ProjectSetupState } from "@/components/dashboard-ui";
import { PaginationControls } from "@/components/pagination-controls";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
  getProjectOnboarding,
} from "@/lib/agent-platform";
import {
  countCriticalIncidents,
  countOpenIncidents,
  formatTimestamp,
} from "@/lib/dashboard";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
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
        title="Create a project before browsing incident history"
        description="Incident history is scoped to a project. Complete onboarding first, then this route will load the ledger, filters, and response status for that project."
      />
    );
  }
  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Incident center"
        title="Finish onboarding before browsing incident history"
        description="Incident history stays in onboarding-first mode until the current project has completed repository connection, secrets setup, and service mapping."
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
  const paginationQuery = { project_id: projectId, status };
  const openCount = countOpenIncidents(incidents);
  const criticalCount = countCriticalIncidents(incidents);

  return (
    <main className="mx-auto max-w-[1280px] space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between pb-5 pt-1">
        <div>
          <h1 className="text-2xl font-semibold text-[#111827]">Incidents</h1>
          <p className="mt-1 text-sm text-[#6b7280]">
            {incidentList.total} total · {openCount} open · {criticalCount} critical
          </p>
        </div>
        <Link
          href="/live"
          className="rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-sm font-medium text-[#374151] shadow-sm transition hover:bg-[#f9fafb]"
        >
          Live view
        </Link>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-[#e5e7eb] bg-white px-5 py-4">
        <form className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[180px]">
            <span className="mb-1.5 block text-xs font-medium text-[#6b7280]">Project</span>
            <input
              type="text"
              name="project_id"
              defaultValue={projectId}
              placeholder="Filter by project"
              className="w-full rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-sm text-[#111827] outline-none focus:border-[#6366f1] focus:ring-1 focus:ring-[#6366f1]"
            />
          </label>
          <label className="w-[140px]">
            <span className="mb-1.5 block text-xs font-medium text-[#6b7280]">Status</span>
            <select
              name="status"
              defaultValue={status ?? ""}
              className="w-full rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-sm text-[#111827] outline-none focus:border-[#6366f1] focus:ring-1 focus:ring-[#6366f1]"
            >
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
            </select>
          </label>
          <label className="w-[140px]">
            <span className="mb-1.5 block text-xs font-medium text-[#6b7280]">Page size</span>
            <select
              name="page_size"
              defaultValue={String(pageSize)}
              className="w-full rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-sm text-[#111827] outline-none focus:border-[#6366f1] focus:ring-1 focus:ring-[#6366f1]"
            >
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
            </select>
          </label>
          <div className="flex items-center gap-2">
            <input type="hidden" name="page" value="1" />
            <button
              type="submit"
              className="rounded-lg bg-[#111827] px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#1f2937]"
            >
              Apply
            </button>
            <Link
              href="/incidents"
              className="rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-sm font-medium text-[#374151] shadow-sm transition hover:bg-[#f9fafb]"
            >
              Reset
            </Link>
          </div>
        </form>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Incident table */}
        <div className="rounded-xl border border-[#e5e7eb] bg-white">
          <div className="border-b border-[#f3f4f6] px-5 py-3">
            <PaginationControls
              pathname="/incidents"
              query={paginationQuery}
              currentPage={currentPage}
              pageSize={pageSize}
              totalItems={incidentList.total}
              itemLabel="incidents"
            />
          </div>

          {incidents.length === 0 ? (
            <div className="px-5 py-20 text-center">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#f3f4f6]">
                <svg className="h-5 w-5 text-[#9ca3af]" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" /></svg>
              </div>
              <p className="text-sm font-medium text-[#374151]">No incidents found</p>
              <p className="mt-1 text-xs text-[#9ca3af]">Try adjusting your filters.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#f3f4f6]">
              {incidents.map((incident) => (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="flex items-center gap-4 px-5 py-3.5 transition hover:bg-[#f9fafb]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={incident.severity} />
                      <StatusBadge status={incident.status} />
                      <span className="text-xs text-[#9ca3af]">{incident.environment}</span>
                    </div>
                    <p className="mt-1.5 truncate text-sm font-medium text-[#111827]">
                      {incident.title}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-[#9ca3af]">
                      {incident.service} · last seen {formatTimestamp(incident.last_seen_at)}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold tabular-nums text-[#111827]">{incident.event_count}</p>
                    <p className="text-[11px] text-[#9ca3af]">events</p>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {incidents.length > 0 ? (
            <div className="border-t border-[#f3f4f6] px-5 py-3">
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
        </div>

        {/* Sidebar: featured incident + stats */}
        <div className="space-y-5">
          {/* Featured incident */}
          <div className="rounded-xl border border-[#e5e7eb] bg-[#111827] p-5 text-white">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-white/50">Latest incident</p>
              {featured ? (
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  featured.status === "open" ? "bg-white/10 text-[#fbbf24]" : "bg-white/10 text-[#34d399]"
                }`}>
                  {featured.status}
                </span>
              ) : null}
            </div>

            {featured ? (
              <div className="mt-3">
                <p className="text-sm font-semibold">{featured.title}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-white/60">
                  {featured.service} · {featured.environment} · {featured.fingerprint.slice(0, 12)}
                </p>

                {featuredAutonomousRun ? (
                  <div className="mt-4 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-medium text-white/50">Autonomous repair</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        featuredAutonomousRun.run.status === "failed"
                          ? "bg-[#dc2626]/20 text-[#fca5a5]"
                          : featuredAutonomousRun.run.status === "running" || featuredAutonomousRun.run.status === "queued"
                            ? "bg-[#3b82f6]/20 text-[#93c5fd]"
                            : featuredAutonomousRun.run.status === "succeeded"
                              ? "bg-[#22c55e]/20 text-[#86efac]"
                              : "bg-white/10 text-white/50"
                      }`}>
                        {featuredAutonomousRun.run.status}
                      </span>
                    </div>
                    {featuredAutonomousRun.run.status === "failed" && featuredAutonomousRun.run.last_error ? (
                      <p className="mt-2 text-xs leading-relaxed text-[#fca5a5]">
                        {truncateAutonomousError(featuredAutonomousRun.run.last_error)}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/10 pt-3">
                  <MiniStat label="Events" value={String(featured.event_count)} />
                  <MiniStat label="Status" value={featured.status} />
                  <MiniStat label="Severity" value={featured.severity} />
                </div>
              </div>
            ) : (
              <p className="mt-3 text-xs text-white/40">No incidents to display.</p>
            )}
          </div>

          {/* Progress timeline */}
          {featured ? (
            <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
              <p className="text-xs font-medium text-[#6b7280]">Incident progress</p>
              <div className="mt-4 space-y-0">
                {buildIncidentProgress(featured).map((step, index) => (
                  <div key={step.title} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f3f4f6] text-[11px] font-semibold text-[#6b7280]">
                        {index + 1}
                      </span>
                      {index < 2 ? <span className="mt-1 h-full w-px bg-[#e5e7eb]" /> : null}
                    </div>
                    <div className="pb-4">
                      <p className="text-sm font-medium text-[#111827]">{step.title}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-[#9ca3af]">{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Quick stats */}
          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-[#e5e7eb] bg-[#e5e7eb]">
            <div className="bg-white px-3 py-3 text-center">
              <p className="text-lg font-semibold tabular-nums text-[#111827]">{incidentList.total}</p>
              <p className="text-[11px] text-[#9ca3af]">Total</p>
            </div>
            <div className="bg-white px-3 py-3 text-center">
              <p className="text-lg font-semibold tabular-nums text-[#111827]">{openCount}</p>
              <p className="text-[11px] text-[#9ca3af]">Open</p>
            </div>
            <div className="bg-white px-3 py-3 text-center">
              <p className="text-lg font-semibold tabular-nums text-[#111827]">{criticalCount}</p>
              <p className="text-[11px] text-[#9ca3af]">Critical</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-white/40">{label}</p>
      <p className="mt-0.5 text-sm font-medium capitalize">{value}</p>
    </div>
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

function buildIncidentProgress(incident: {
  title: string;
  service: string;
  status: string;
  last_seen_at: string;
  event_count: number;
}) {
  return [
    {
      title: "Detected",
      detail: `${incident.service} crossed the alert threshold.`,
    },
    {
      title: "Under review",
      detail: `${incident.event_count} events attached for investigation.`,
    },
    {
      title: `Status: ${incident.status}`,
      detail: "Awaiting resolution or additional response actions.",
    },
  ];
}

function truncateAutonomousError(error: string): string {
  return error.length <= 120 ? error : `${error.slice(0, 117)}…`;
}

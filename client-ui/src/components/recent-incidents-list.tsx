"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { formatTimestamp } from "@/lib/dashboard";
import type {
  AutonomousRunStatus,
  IncidentAutonomousRunDetail,
  IncidentSummary,
} from "@/lib/types";

type RecentIncidentsListProps = {
  incidents: IncidentSummary[];
  autonomousRuns?: Record<string, IncidentAutonomousRunDetail | null>;
  title?: string;
  emptyTitle?: string;
  emptySubtitle?: string;
  viewAllHref?: string;
  pageSize?: number;
  selectedIncidentId?: string | null;
  onSelectIncident?: (incidentId: string) => void;
  className?: string;
};

export function RecentIncidentsList({
  incidents,
  autonomousRuns = {},
  title = "Recent Incidents",
  emptyTitle = "All clear",
  emptySubtitle = "No incidents recorded yet.",
  viewAllHref,
  pageSize = 6,
  selectedIncidentId = null,
  onSelectIncident,
  className = "",
}: RecentIncidentsListProps) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(incidents.length / pageSize));

  useEffect(() => {
    setPage(1);
  }, [incidents, pageSize]);

  const currentPage = Math.min(page, totalPages);
  const pagedIncidents = useMemo(
    () => incidents.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [currentPage, incidents, pageSize],
  );

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden rounded-2xl border border-white/[0.06] bg-[#0d1119] ${className}`.trim()}
    >
      <div className="h-[2px] w-full shrink-0 bg-[#ff6a3d]/65" aria-hidden />
      <div className="flex items-center justify-between px-5 py-3">
        <p className="text-sm font-semibold text-white/90">{title}</p>
        {viewAllHref ? (
          <Link href={viewAllHref} className="text-xs font-medium text-[#ff8c5a] hover:text-[#ffb99a]">
            View all →
          </Link>
        ) : null}
      </div>

      {incidents.length === 0 ? (
        <div className="flex flex-1 items-center justify-center py-12">
          <div className="text-center">
            <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-[rgba(32,201,51,0.12)]">
              <svg className="h-4 w-4 text-[#20c933]" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-white/80">{emptyTitle}</p>
            <p className="mt-0.5 text-xs text-white/40">{emptySubtitle}</p>
          </div>
        </div>
      ) : (
        <>
          <div className="flex-1 divide-y divide-white/[0.04]">
            {pagedIncidents.map((incident) =>
              onSelectIncident ? (
                <button
                  key={incident.id}
                  type="button"
                  onClick={() => onSelectIncident(incident.id)}
                  className={`flex w-full items-center gap-3 border-l-2 px-5 py-3 text-left transition ${
                    selectedIncidentId === incident.id
                      ? "border-[#ff6a3d] bg-[rgba(255,106,61,0.06)]"
                      : "border-transparent hover:border-white/[0.08] hover:bg-white/[0.03]"
                  }`}
                >
                  <IncidentRowContent
                    incident={incident}
                    selected={selectedIncidentId === incident.id}
                    runStatus={autonomousRuns[incident.id]?.run.status ?? null}
                  />
                </button>
              ) : (
                <Link
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="flex items-center gap-3 border-l-2 border-transparent px-5 py-3 transition hover:border-white/[0.08] hover:bg-white/[0.03]"
                >
                  <IncidentRowContent
                    incident={incident}
                    selected={false}
                    runStatus={autonomousRuns[incident.id]?.run.status ?? null}
                  />
                </Link>
              ),
            )}
          </div>
          {totalPages > 1 ? (
            <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-2.5">
              <p className="text-xs text-white/30">
                {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, incidents.length)} of {incidents.length}
              </p>
              <div className="flex items-center gap-1">
                <PgBtn onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage <= 1}>
                  ←
                </PgBtn>
                {buildPageWindow(currentPage, totalPages).map((value, index) =>
                  value === 0 ? (
                    <span key={`ellipsis-${index}`} className="px-1 text-xs text-white/20">
                      …
                    </span>
                  ) : (
                    <PgBtn key={value} onClick={() => setPage(value)} active={value === currentPage}>
                      {value}
                    </PgBtn>
                  ),
                )}
                <PgBtn onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={currentPage >= totalPages}>
                  →
                </PgBtn>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function IncidentRowContent({
  incident,
  selected,
  runStatus,
}: {
  incident: IncidentSummary;
  selected: boolean;
  runStatus: AutonomousRunStatus | null;
}) {
  return (
    <>
      <div className="min-w-0 flex-1">
        <p className={`truncate text-sm font-medium ${selected ? "text-white" : "text-white/90"}`}>
          {incident.title}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={incident.severity} />
          <StatusBadge status={incident.status} />
          {runStatus ? <RunBadge status={runStatus} /> : null}
          <span className="text-[11px] text-white/30">
            {incident.service} · {formatTimestamp(incident.last_seen_at)}
          </span>
        </div>
      </div>
      <div
        className="shrink-0 text-right"
        title={`${incident.event_count} telemetry ${incident.event_count === 1 ? "event" : "events"} grouped into this incident`}
      >
        <p className="text-sm font-semibold tabular-nums text-white/70">{incident.event_count}</p>
        <p className="text-[10px] font-medium uppercase tracking-wide text-white/35">
          {incident.event_count === 1 ? "event" : "events"}
        </p>
      </div>
    </>
  );
}

function RunBadge({ status }: { status: AutonomousRunStatus }) {
  const badgeMap: Record<AutonomousRunStatus, { label: string; className: string }> = {
    failed: { label: "Repair failed", className: "bg-[rgba(248,43,96,0.12)] text-[#ff6b8a]" },
    running: { label: "Repairing", className: "bg-[rgba(45,127,249,0.12)] text-[#6fa8ff]" },
    queued: { label: "Queued", className: "bg-[rgba(45,127,249,0.12)] text-[#6fa8ff]" },
    succeeded: { label: "Repaired", className: "bg-[rgba(32,201,51,0.12)] text-[#5edd78]" },
    cancelled: { label: "Cancelled", className: "bg-white/5 text-white/40" },
  };
  const badge = badgeMap[status];
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.className}`}>{badge.label}</span>;
}

function PgBtn({
  onClick,
  disabled,
  active,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-2 py-1 text-xs font-medium transition ${
        active
          ? "bg-[#ff6a3d] text-white"
          : disabled
            ? "text-white/15"
            : "text-white/50 hover:bg-white/[0.06]"
      }`}
    >
      {children}
    </button>
  );
}

function buildPageWindow(currentPage: number, totalPages: number): number[] {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (currentPage <= 3) return [1, 2, 3, 4, 0, totalPages];
  if (currentPage >= totalPages - 2) return [1, 0, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  return [1, 0, currentPage - 1, currentPage, currentPage + 1, 0, totalPages];
}

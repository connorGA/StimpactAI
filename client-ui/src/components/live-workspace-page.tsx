"use client";

import Link from "next/link";
import { useMemo, useState, useEffect } from "react";

import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import type {
  AutonomousRunStatus,
  IncidentAutonomousRunDetail,
  IncidentReportingOverview,
  IncidentSummary,
  ProjectTelemetryVerification,
} from "@/lib/types";

const PAGE_SIZE = 6;

const DONUT_COLORS = ["#ff6a3d", "#ffb253", "#18bfff", "#20c933", "#8b46ff", "#f82b60", "#2d7ff9", "#64748b"];

type ChartRange = "24h" | "7d" | "30d" | "1y" | "all";
const RANGE_LABELS: Record<ChartRange, string> = { "24h": "24 Hours", "7d": "7 Days", "30d": "30 Days", "1y": "1 Year", all: "All Time" };
const RANGE_MS: Record<ChartRange, number> = { "24h": 86_400_000, "7d": 7 * 86_400_000, "30d": 30 * 86_400_000, "1y": 365 * 86_400_000, all: Infinity };

type Props = {
  projectId: string;
  incidents: IncidentSummary[];
  reporting: IncidentReportingOverview;
  autonomousRuns: Record<string, IncidentAutonomousRunDetail | null>;
  sdkDefaultService: string;
};

type ChartView = "timeline" | "heatmap";

export function LiveDashboard({ projectId, incidents, reporting, autonomousRuns, sdkDefaultService }: Props) {
  const [page, setPage] = useState(1);
  const [chartRange, setChartRange] = useState<ChartRange>("30d");
  const [chartView, setChartView] = useState<ChartView>("timeline");
  const [sdkVerification, setSdkVerification] = useState<ProjectTelemetryVerification | null>(null);

  useEffect(() => {
    if (!sdkDefaultService) return;
    const check = async () => {
      try {
        const params = new URLSearchParams({ service: sdkDefaultService, environment: "production" });
        const res = await fetch(`/api/onboarding/projects/${projectId}/telemetry-verification?${params}`);
        if (res.ok) setSdkVerification(await res.json());
      } catch { /* silent */ }
    };
    void check();
    const iv = setInterval(check, 30_000);
    return () => clearInterval(iv);
  }, [projectId, sdkDefaultService]);

  const rangeIncidents = useMemo(() => filterByRange(incidents, chartRange), [incidents, chartRange]);

  const trendPoints = useMemo(() => buildTrendPoints(rangeIncidents, chartRange, reporting), [rangeIncidents, chartRange, reporting]);
  const serviceBreakdown = useMemo(() => {
    const m = new Map<string, number>();
    for (const inc of rangeIncidents) m.set(inc.service, (m.get(inc.service) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([label, count]) => ({ label, count }));
  }, [rangeIncidents]);

  const pagedIncidents = incidents.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(incidents.length / PAGE_SIZE));
  const globalOpen = reporting.open_incidents;
  const hasRepair = incidents.some((i) => i.status === "open" && (autonomousRuns[i.id]?.run.status === "running" || autonomousRuns[i.id]?.run.status === "queued"));

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-12 pt-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <SdkBadge verification={sdkVerification} />
          {globalOpen > 0 && (
            <Link href="/incidents" className="flex items-center gap-1.5 rounded-full border border-[rgba(255,106,61,0.3)] bg-[rgba(255,106,61,0.12)] px-2.5 py-1 transition hover:bg-[rgba(255,106,61,0.2)]">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff6a3d] opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#ff6a3d]" />
              </span>
              <span className="text-[11px] font-semibold text-[#ffb99a]">
                {globalOpen} active incident{globalOpen !== 1 ? "s" : ""}{hasRepair ? " · repairing" : ""}
              </span>
            </Link>
          )}
        </div>
        <Link href="/incidents" className="rounded-lg border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.08]">
          Incident History
        </Link>
      </div>

      {/* Stats — rolling 30d (fixed window from reporting API); chart filters below do not change these */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <LiveMetricCard
          label="Uptime"
          hint="% of days in the last 30d with no new incident"
          value={`${reporting.uptime_percent_last_30d.toFixed(1)}%`}
          delta={{ value: reporting.uptime_delta_pp, mode: "higherIsGood", format: "percent" }}
        />
        <LiveMetricCard
          label="Avg response time"
          hint="Mean time from first signal to agent fix (autonomous), last 30d"
          value={
            reporting.avg_agent_response_seconds_last_30d == null
              ? "—"
              : fmtDurationSeconds(reporting.avg_agent_response_seconds_last_30d)
          }
          delta={
            reporting.avg_agent_response_delta_seconds == null
              ? null
              : {
                  value: reporting.avg_agent_response_delta_seconds,
                  mode: "lowerIsGood",
                  format: "seconds",
                }
          }
        />
        <LiveMetricCard
          label="Open incidents"
          hint="Currently open incidents"
          value={reporting.open_incidents === 0 ? "None" : String(reporting.open_incidents)}
          valueClassName={reporting.open_incidents === 0 ? "text-[#20c933]" : "text-[#ff6a3d]"}
        />
        <LiveMetricCard
          label="Agent resolution rate"
          hint="% of incidents resolved by the agent in the last 30d"
          value={
            reporting.agent_resolution_percent_last_30d == null
              ? "—"
              : `${reporting.agent_resolution_percent_last_30d.toFixed(1)}%`
          }
          delta={
            reporting.agent_resolution_delta_pp == null
              ? null
              : { value: reporting.agent_resolution_delta_pp, mode: "higherIsGood", format: "percent" }
          }
        />
      </div>

      {/* Chart */}
      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[linear-gradient(180deg,rgba(16,20,30,0.95),rgba(10,14,22,0.98))]">
        <div className="flex items-center justify-between px-5 pt-5 pb-2">
          <div className="flex items-center gap-3">
            <p className="text-sm font-semibold text-white/90">
              {chartView === "timeline" ? "Incidents over time" : "Incident Heatmap"}
            </p>
            <div className="flex items-center gap-0.5 rounded-lg border border-white/8 bg-white/[0.03] p-0.5">
              <button onClick={() => setChartView("timeline")}
                className={`rounded-md px-2 py-1 text-[11px] font-medium transition ${chartView === "timeline" ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white/60"}`}>
                <svg className="inline-block h-3 w-3 mr-1" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12 4 6l3 4 3-8 3 6" />
                </svg>
                Timeline
              </button>
              <button onClick={() => setChartView("heatmap")}
                className={`rounded-md px-2 py-1 text-[11px] font-medium transition ${chartView === "heatmap" ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white/60"}`}>
                <svg className="inline-block h-3 w-3 mr-1" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="1" y="1" width="4" height="4" rx="0.5" />
                  <rect x="6" y="1" width="4" height="4" rx="0.5" />
                  <rect x="11" y="1" width="4" height="4" rx="0.5" />
                  <rect x="1" y="6" width="4" height="4" rx="0.5" />
                  <rect x="6" y="6" width="4" height="4" rx="0.5" />
                  <rect x="11" y="6" width="4" height="4" rx="0.5" />
                  <rect x="1" y="11" width="4" height="4" rx="0.5" />
                  <rect x="6" y="11" width="4" height="4" rx="0.5" />
                  <rect x="11" y="11" width="4" height="4" rx="0.5" />
                </svg>
                Heatmap
              </button>
            </div>
          </div>
          {chartView === "timeline" && (
            <div className="flex items-center gap-0.5 rounded-lg border border-white/8 bg-white/[0.03] p-0.5">
              {(Object.keys(RANGE_LABELS) as ChartRange[]).map((r) => (
                <button key={r} onClick={() => setChartRange(r)}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${chartRange === r ? "bg-white/10 text-white shadow-sm" : "text-white/40 hover:text-white/60"}`}>
                  {RANGE_LABELS[r]}
                </button>
              ))}
            </div>
          )}
          {chartView === "heatmap" && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-white/30">No incidents</span>
              <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#20c933" }} />
              <span className="mx-1 text-[10px] text-white/20">→</span>
              <div className="flex items-center gap-1">
                {["rgba(255,106,61,0.3)", "rgba(255,106,61,0.5)", "#ff6a3d", "#ff4510"].map((c, i) => (
                  <span key={i} className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: c }} />
                ))}
              </div>
              <span className="text-[10px] text-white/30">More</span>
            </div>
          )}
        </div>
        <div className="px-3 pb-4">
          {chartView === "timeline"
            ? <TrendChart points={trendPoints} range={chartRange} />
            : <IncidentHeatmap incidents={incidents} />
          }
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Donut */}
        <div className="flex min-h-[min(360px,55vw)] flex-col rounded-2xl border border-white/[0.06] bg-[rgba(14,18,28,0.9)]">
          {serviceBreakdown.length === 0 ? (
            <>
              <p className="px-5 pt-5 text-sm font-semibold text-white/90">Incidents by Service</p>
              <Empty text="No service data yet" />
            </>
          ) : (
            <>
              <div className="flex shrink-0 items-start justify-between gap-3 px-5 pt-5">
                <p className="text-sm font-semibold text-white/90">Incidents by Service</p>
                <DonutLegendCompact data={serviceBreakdown} total={rangeIncidents.length} />
              </div>
              <div className="flex min-h-[min(260px,35vh)] flex-1 items-center justify-center px-4 pb-6 pt-2">
                <div className="aspect-square w-full max-w-[min(280px,78%)]">
                  <DonutChart data={serviceBreakdown} size={280} />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Incident list */}
        <div className="flex flex-col rounded-2xl border border-white/[0.06] bg-[rgba(14,18,28,0.9)]">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
            <p className="text-sm font-semibold text-white/90">Recent Incidents</p>
            <Link href="/incidents" className="text-xs font-medium text-[#ff8c5a] hover:text-[#ffb99a]">View all →</Link>
          </div>

          {incidents.length === 0 ? (
            <div className="flex flex-1 items-center justify-center py-12">
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-[rgba(32,201,51,0.12)]">
                  <svg className="h-4 w-4 text-[#20c933]" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-white/80">All clear</p>
                <p className="mt-0.5 text-xs text-white/40">No incidents recorded yet.</p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex-1 divide-y divide-white/[0.04]">
                {pagedIncidents.map((inc) => (
                  <Link key={inc.id} href={`/incidents/${inc.id}`} className="flex items-center gap-3 px-5 py-3 transition hover:bg-white/[0.03]">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-white/90">{inc.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <SeverityBadge severity={inc.severity} />
                        <StatusBadge status={inc.status} />
                        {autonomousRuns[inc.id] && <RunBadge status={autonomousRuns[inc.id]!.run.status} />}
                        <span className="text-[11px] text-white/30">{inc.service} · {fmtTime(inc.last_seen_at)}</span>
                      </div>
                    </div>
                    <div
                      className="shrink-0 text-right"
                      title={`${inc.event_count} telemetry ${inc.event_count === 1 ? "event" : "events"} grouped into this incident`}
                    >
                      <p className="text-sm font-semibold tabular-nums text-white/70">{inc.event_count}</p>
                      <p className="text-[10px] font-medium uppercase tracking-wide text-white/35">
                        {inc.event_count === 1 ? "event" : "events"}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-2.5">
                  <p className="text-xs text-white/30">{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, incidents.length)} of {incidents.length}</p>
                  <div className="flex items-center gap-1">
                    <PgBtn onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>←</PgBtn>
                    {pgNums(page, totalPages).map((n, i) =>
                      n === 0 ? <span key={`e${i}`} className="px-1 text-xs text-white/20">…</span>
                        : <PgBtn key={n} onClick={() => setPage(n)} active={n === page}>{n}</PgBtn>
                    )}
                    <PgBtn onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>→</PgBtn>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}

// ── SDK badge ──

function SdkBadge({ verification }: { verification: ProjectTelemetryVerification | null }) {
  const h = verification?.status === "healthy";
  const s = verification?.status === "stale";
  const ping = verification?.last_seen_at;
  let label = "SDK waiting";
  let dot = "bg-white/30";
  let bg = "border-white/8 bg-white/[0.03]";
  if (h) { label = "SDK connected"; dot = "bg-[#20c933]"; bg = "border-[rgba(32,201,51,0.2)] bg-[rgba(32,201,51,0.08)]"; }
  else if (s) { label = "SDK stale"; dot = "bg-[#ffb253]"; bg = "border-[rgba(255,178,83,0.2)] bg-[rgba(255,178,83,0.08)]"; }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${bg}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className="text-[11px] font-medium text-white/70">{label}</span>
      {ping && <span className="text-[10px] text-white/30">· {fmtShort(ping)}</span>}
    </span>
  );
}

// ── Live metric cards ──

type MetricDelta = {
  value: number;
  mode: "higherIsGood" | "lowerIsGood";
  format: "percent" | "seconds";
};

function LiveMetricCard({
  label,
  hint,
  value,
  valueClassName,
  delta,
}: {
  label: string;
  hint?: string;
  value: string;
  valueClassName?: string;
  delta?: MetricDelta | null;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[rgba(14,18,28,0.8)] px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 text-[11px] font-medium uppercase tracking-wider text-white/40" title={hint}>
          {label}
        </p>
        {delta ? (
          <div className="shrink-0">
            <MetricDeltaBadge delta={delta} />
          </div>
        ) : null}
      </div>
      <p className={`mt-1.5 text-2xl font-bold tabular-nums ${valueClassName ?? "text-white"}`}>{value}</p>
    </div>
  );
}

function MetricDeltaBadge({ delta }: { delta: MetricDelta }) {
  const { value: raw, mode, format } = delta;
  if (Number.isNaN(raw)) return null;

  const good =
    raw === 0 ? null : mode === "higherIsGood" ? raw > 0 : raw < 0;
  const up = raw > 0;

  let text: string;
  if (format === "percent") {
    text = `${Math.abs(raw).toFixed(1)}%`;
  } else {
    text = formatAbsDurationSeconds(Math.abs(raw));
  }

  const base =
    "inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums leading-none";
  if (raw === 0) {
    return (
      <span className={`${base} border-white/10 bg-white/[0.06] text-white/45`} title="Change vs prior 30 days">
        <span aria-hidden>→</span>
        {format === "percent" ? "0%" : "0s"}
      </span>
    );
  }
  const tone =
    good === true
      ? "border-[rgba(32,201,51,0.35)] bg-[rgba(32,201,51,0.12)] text-[#4ade80]"
      : "border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.1)] text-[#fca5a5]";

  return (
    <span className={`${base} ${tone}`} title="Change vs prior 30 days">
      <span aria-hidden className="text-[10px] leading-none">
        {up ? "↑" : "↓"}
      </span>
      {text}
    </span>
  );
}

function fmtDurationSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function formatAbsDurationSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

// ── Trend chart ──

function TrendChart({ points, range }: { points: { label: string; count: number }[]; range: ChartRange }) {
  if (points.length === 0) return <Empty text="No trend data yet" />;

  const W = 900;
  const H = 220;
  const PL = 38;
  const PR = 12;
  const PT = 18;
  const PB = 30;
  const cW = W - PL - PR;
  const cH = H - PT - PB;

  const vals = points.map((p) => p.count);
  const maxVal = Math.max(...vals, 1);
  const yTicks = niceY(maxVal);
  const yMax = yTicks[yTicks.length - 1] ?? maxVal;

  const toX = (i: number) => PL + (i / Math.max(points.length - 1, 1)) * cW;
  const toY = (v: number) => PT + (1 - v / yMax) * cH;

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p.count).toFixed(1)}`).join(" ");
  const area = `${line} L ${toX(points.length - 1).toFixed(1)} ${(H - PB).toFixed(1)} L ${PL} ${(H - PB).toFixed(1)} Z`;
  const xInt = xInterval(points.length, range);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full">
      <defs>
        <linearGradient id="chartGlow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff6a3d" stopOpacity="0.25" />
          <stop offset="60%" stopColor="#ff6a3d" stopOpacity="0.06" />
          <stop offset="100%" stopColor="#ff6a3d" stopOpacity="0" />
        </linearGradient>
        <filter id="lineGlow">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3" />
        </filter>
      </defs>

      {yTicks.map((t) => (
        <g key={t}>
          <line x1={PL} y1={toY(t)} x2={W - PR} y2={toY(t)} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          <text x={PL - 8} y={toY(t) + 3.5} textAnchor="end" className="fill-[rgba(255,255,255,0.25)] text-[9px]">{fmtYTick(t)}</text>
        </g>
      ))}

      <path d={area} fill="url(#chartGlow)" />
      <path d={line} fill="none" stroke="#ff6a3d" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" filter="url(#lineGlow)" opacity="0.5" />
      <path d={line} fill="none" stroke="#ff6a3d" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

      {points.map((p, i) => (
        <g key={i}>
          <circle cx={toX(i)} cy={toY(p.count)} r="5" fill="#ff6a3d" opacity="0.15" />
          <circle cx={toX(i)} cy={toY(p.count)} r="3" fill="#0e121c" stroke="#ff6a3d" strokeWidth="1.5" />
        </g>
      ))}

      {points.map((p, i) => {
        if (i % xInt !== 0 && i !== points.length - 1) return null;
        return <text key={`xl-${i}`} x={toX(i)} y={H - 6} textAnchor="middle" className="fill-[rgba(255,255,255,0.3)] text-[9px]">{p.label}</text>;
      })}
    </svg>
  );
}

// ── Incident heatmap ──

function IncidentHeatmap({ incidents }: { incidents: IncidentSummary[] }) {
  const incidentsByDay = useMemo(() => {
    const m = new Map<string, number>();
    for (const inc of incidents) {
      const d = new Date(inc.last_seen_at);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      m.set(key, (m.get(key) ?? 0) + 1);
    }
    return m;
  }, [incidents]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - startDate.getDay());
  startDate.setDate(startDate.getDate() - 52 * 7);

  const endDate = new Date(today);
  endDate.setDate(endDate.getDate() + (6 - endDate.getDay()));

  const weeks: { date: Date; key: string; count: number }[][] = [];
  const cur = new Date(startDate);
  let week: { date: Date; key: string; count: number }[] = [];

  while (cur <= endDate) {
    const key = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
    const count = incidentsByDay.get(key) ?? 0;
    const isFuture = cur > today;
    week.push({ date: new Date(cur), key, count: isFuture ? -1 : count });

    if (cur.getDay() === 6) {
      weeks.push(week);
      week = [];
    }
    cur.setDate(cur.getDate() + 1);
  }
  if (week.length > 0) weeks.push(week);

  const maxCount = Math.max(1, ...incidents.map(() => 1), ...[...incidentsByDay.values()]);

  const cellSize = 11;
  const cellGap = 2;
  const step = cellSize + cellGap;
  const rowLabelWidth = 28;
  const topPad = 18;
  const svgW = rowLabelWidth + weeks.length * step + 4;
  const svgH = topPad + 7 * step + 2;

  const monthLabels: { x: number; label: string }[] = [];
  let lastMonth = -1;
  for (let w = 0; w < weeks.length; w++) {
    const firstDay = weeks[w][0];
    if (!firstDay) continue;
    const mo = firstDay.date.getMonth();
    if (mo !== lastMonth) {
      monthLabels.push({
        x: rowLabelWidth + w * step,
        label: firstDay.date.toLocaleDateString("en-US", { month: "short" }),
      });
      lastMonth = mo;
    }
  }

  const dayLabels = ["", "Mon", "", "Wed", "", "Fri", ""];

  function cellColor(count: number): string {
    if (count < 0) return "rgba(255,255,255,0.02)";
    if (count === 0) return "#20c933";
    const t = Math.min(count / Math.max(maxCount, 1), 1);
    if (t <= 0.25) return "rgba(255,106,61,0.3)";
    if (t <= 0.5) return "rgba(255,106,61,0.5)";
    if (t <= 0.75) return "#ff6a3d";
    return "#ff4510";
  }

  const [hovered, setHovered] = useState<{ key: string; count: number; x: number; y: number } | null>(null);

  return (
    <div className="relative w-full" style={{ overflow: "visible" }}>
      <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full" style={{ minWidth: 680, overflow: "visible" }}>
        {monthLabels.map((m, i) => (
          <text key={i} x={m.x} y={11} className="fill-[rgba(255,255,255,0.3)] text-[9px]">{m.label}</text>
        ))}

        {dayLabels.map((lbl, row) =>
          lbl ? (
            <text key={row} x={rowLabelWidth - 5} y={topPad + row * step + cellSize - 2} textAnchor="end" className="fill-[rgba(255,255,255,0.25)] text-[8px]">{lbl}</text>
          ) : null
        )}

        {weeks.map((wk, wi) =>
          wk.map((d) => {
            const dow = d.date.getDay();
            const x = rowLabelWidth + wi * step;
            const y = topPad + dow * step;
            return (
              <rect
                key={d.key}
                x={x}
                y={y}
                width={cellSize}
                height={cellSize}
                rx={2}
                fill={cellColor(d.count)}
                className="transition-colors duration-100"
                onMouseEnter={(e) => {
                  const rect = (e.target as SVGElement).getBoundingClientRect();
                  setHovered({ key: d.key, count: d.count, x: rect.left + rect.width / 2, y: rect.top });
                }}
                onMouseLeave={() => setHovered(null)}
              />
            );
          })
        )}
      </svg>

      {hovered && hovered.count >= 0 && (
        <div
          className="pointer-events-none fixed z-50 whitespace-nowrap rounded-md border border-white/10 bg-[#141822] px-2.5 py-1.5 text-[11px] text-white/80 shadow-lg"
          style={{
            left: hovered.x,
            top: hovered.y,
            transform: "translate(-50%, calc(-100% - 8px))",
          }}
        >
          <span className="font-semibold">{hovered.count} incident{hovered.count !== 1 ? "s" : ""}</span>
          <span className="text-white/40 ml-1.5">{formatHeatmapDate(hovered.key)}</span>
        </div>
      )}
    </div>
  );
}

function formatHeatmapDate(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y!, m! - 1, d);
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

// ── Donut ──

function DonutChart({ data, size = 150 }: { data: { label: string; count: number }[]; size?: number }) {
  const total = data.reduce((s, d) => s + d.count, 0) || 1;
  const R = size / 2;
  const SW = size * 0.15;
  const r = R - SW / 2;
  const C = 2 * Math.PI * r;
  let off = 0;
  const labelFs = Math.max(14, Math.round(size * 0.09));
  const subFs = Math.max(9, Math.round(size * 0.042));
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full max-h-[min(280px,42vh)] shrink-0" preserveAspectRatio="xMidYMid meet">
      {data.map((d, i) => {
        const dash = (d.count / total) * C;
        const el = <circle key={d.label} cx={R} cy={R} r={r} fill="none" stroke={DONUT_COLORS[i % DONUT_COLORS.length]} strokeWidth={SW} strokeDasharray={`${dash} ${C - dash}`} strokeDashoffset={-off} transform={`rotate(-90 ${R} ${R})`} />;
        off += dash;
        return el;
      })}
      <text x={R} y={R - size * 0.02} textAnchor="middle" className="fill-white font-bold" style={{ fontSize: labelFs }}>{total}</text>
      <text x={R} y={R + size * 0.08} textAnchor="middle" className="fill-white/40" style={{ fontSize: subFs }}>incidents</text>
    </svg>
  );
}

function DonutLegendCompact({ data, total }: { data: { label: string; count: number }[]; total: number }) {
  const t = total || 1;
  return (
    <div className="max-w-[min(200px,45%)] shrink-0 text-right">
      {data.slice(0, 8).map((d, i) => (
        <div key={d.label} className="flex items-center justify-end gap-1.5 py-0.5 text-[10px] leading-tight">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: DONUT_COLORS[i % DONUT_COLORS.length] }} />
          <span className="max-w-[7rem] truncate text-white/55">{d.label}</span>
          <span className="shrink-0 font-semibold tabular-nums text-white/85">{d.count}</span>
          <span className="shrink-0 tabular-nums text-[#ff8c5a]">{((d.count / t) * 100).toFixed(0)}%</span>
        </div>
      ))}
    </div>
  );
}

// ── Run badge ──

function RunBadge({ status }: { status: AutonomousRunStatus }) {
  const m: Record<string, { l: string; c: string }> = {
    failed: { l: "Repair failed", c: "bg-[rgba(248,43,96,0.12)] text-[#ff6b8a]" },
    running: { l: "Repairing", c: "bg-[rgba(45,127,249,0.12)] text-[#6fa8ff]" },
    queued: { l: "Queued", c: "bg-[rgba(45,127,249,0.12)] text-[#6fa8ff]" },
    succeeded: { l: "Repaired", c: "bg-[rgba(32,201,51,0.12)] text-[#5edd78]" },
    cancelled: { l: "Cancelled", c: "bg-white/5 text-white/40" },
  };
  const { l, c } = m[status] ?? m.cancelled!;
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${c}`}>{l}</span>;
}

// ── Helpers ──

function Empty({ text }: { text: string }) {
  return <div className="flex h-40 items-center justify-center text-xs text-white/30">{text}</div>;
}

function PgBtn({ onClick, disabled, active, children }: { onClick: () => void; disabled?: boolean; active?: boolean; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`rounded px-2 py-1 text-xs font-medium transition ${active ? "bg-[#ff6a3d] text-white" : disabled ? "text-white/15" : "text-white/50 hover:bg-white/[0.06]"}`}>
      {children}
    </button>
  );
}

function pgNums(cur: number, tot: number): number[] {
  if (tot <= 5) return Array.from({ length: tot }, (_, i) => i + 1);
  if (cur <= 3) return [1, 2, 3, 4, 0, tot];
  if (cur >= tot - 2) return [1, 0, tot - 3, tot - 2, tot - 1, tot];
  return [1, 0, cur - 1, cur, cur + 1, 0, tot];
}

function filterByRange(incidents: IncidentSummary[], range: ChartRange): IncidentSummary[] {
  if (range === "all") return incidents;
  const cut = Date.now() - RANGE_MS[range];
  return incidents.filter((i) => new Date(i.last_seen_at).getTime() >= cut);
}

function buildTrendPoints(ri: IncidentSummary[], range: ChartRange, rep: IncidentReportingOverview) {
  if (range === "24h") return hourly(ri);
  if (range === "7d") return daily(ri, 7);
  if (range === "30d") return daily(ri, 30);
  return monthly(ri);
}

function hourly(incs: IncidentSummary[]) {
  const now = new Date();
  return Array.from({ length: 24 }, (_, i) => {
    const s = new Date(now); s.setHours(now.getHours() - 23 + i, 0, 0, 0);
    const e = new Date(s); e.setHours(s.getHours() + 1);
    return { label: s.toLocaleTimeString("en-US", { hour: "numeric", hour12: true }), count: incs.filter((x) => { const t = new Date(x.last_seen_at).getTime(); return t >= s.getTime() && t < e.getTime(); }).length };
  });
}

function daily(incs: IncidentSummary[], days: number) {
  const now = new Date();
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(now); d.setDate(now.getDate() - days + 1 + i); d.setHours(0, 0, 0, 0);
    const n = new Date(d); n.setDate(d.getDate() + 1);
    const label = days <= 7 ? d.toLocaleDateString("en-US", { weekday: "short" }) : `${d.getMonth() + 1}/${d.getDate()}`;
    return { label, count: incs.filter((x) => { const t = new Date(x.last_seen_at).getTime(); return t >= d.getTime() && t < n.getTime(); }).length };
  });
}

function monthly(incs: IncidentSummary[]) {
  const now = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const s = new Date(now.getFullYear(), now.getMonth() - 11 + i, 1);
    const e = new Date(s.getFullYear(), s.getMonth() + 1, 1);
    return { label: s.toLocaleDateString("en-US", { month: "short" }), count: incs.filter((x) => { const t = new Date(x.last_seen_at).getTime(); return t >= s.getTime() && t < e.getTime(); }).length };
  });
}

function dateLbl(raw: string) {
  try { const d = new Date(raw); return isNaN(d.getTime()) ? raw : d.toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
  catch { return raw; }
}

function niceY(max: number): number[] {
  if (max === 0) return [0];
  if (max <= 4) return Array.from({ length: max + 1 }, (_, i) => i);
  const raw = max / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  let step = [1, 2, 2.5, 5, 10].find((n) => n * mag >= raw)! * mag;
  if (!step) step = Math.ceil(raw);
  if (max <= 10) step = Math.max(1, Math.round(step));
  const ticks: number[] = [];
  for (let t = 0; t <= max + step * 0.01; t += step) { ticks.push(Math.round(t * 100) / 100); if (ticks.length >= 6) break; }
  if (ticks[ticks.length - 1]! < max) ticks.push(ticks[ticks.length - 1]! + step);
  return ticks;
}

function fmtYTick(n: number) { return n >= 1e6 ? `${(n / 1e6).toFixed(0)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(0)}K` : String(Math.round(n)); }
function xInterval(count: number, range: ChartRange) { if (range === "24h") return Math.max(1, Math.ceil(count / 12)); if (range === "7d") return 1; if (range === "1y") return 1; return Math.max(1, Math.ceil(count / 10)); }
function fmtBig(n: number) { return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n); }
function fmtTime(ts: string) { return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(ts)); }
function fmtShort(ts: string) { return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(ts)); }

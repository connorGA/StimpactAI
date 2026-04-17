"use client";

import Link from "next/link";
import { useMemo, useState, useEffect } from "react";

import {
  DashboardMetricCard,
  formatMetricDurationSeconds,
} from "@/components/dashboard-metric-cards";
import { RecentIncidentsList } from "@/components/recent-incidents-list";
import type {
  IncidentAutonomousRunDetail,
  IncidentLiveStreamPayload,
  IncidentReportingOverview,
  IncidentSummary,
  ProjectTelemetryVerification,
} from "@/lib/types";

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
  const [chartRange, setChartRange] = useState<ChartRange>("30d");
  const [chartView, setChartView] = useState<ChartView>("timeline");
  const [sdkVerification, setSdkVerification] = useState<ProjectTelemetryVerification | null>(null);
  const [liveSnapshot, setLiveSnapshot] = useState<IncidentLiveStreamPayload | null>(null);

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

  useEffect(() => {
    const source = new EventSource(`/api/incidents/live-stream?project_id=${encodeURIComponent(projectId)}`);
    source.onmessage = (event) => {
      try {
        setLiveSnapshot(JSON.parse(event.data) as IncidentLiveStreamPayload);
      } catch {
        // Keep the last good snapshot.
      }
    };
    return () => source.close();
  }, [projectId]);

  const rangeIncidents = useMemo(() => filterByRange(incidents, chartRange), [incidents, chartRange]);

  const trendPoints = useMemo(() => buildTrendPoints(rangeIncidents, chartRange), [rangeIncidents, chartRange]);
  const serviceBreakdown = useMemo(() => {
    const m = new Map<string, number>();
    for (const inc of rangeIncidents) m.set(inc.service, (m.get(inc.service) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([label, count]) => ({ label, count }));
  }, [rangeIncidents]);

  const mergedAutonomousRuns = useMemo(() => {
    if (!liveSnapshot) {
      return autonomousRuns;
    }
    const next = { ...autonomousRuns };
    for (const transition of liveSnapshot.recent_transitions) {
      const existing = next[transition.incident_id];
      if (!existing) {
        continue;
      }
      next[transition.incident_id] = {
        ...existing,
        run: {
          ...existing.run,
          status: transition.status,
          phase: transition.phase,
          promotion_url: transition.promotion_url,
          updated_at: transition.updated_at,
        },
      };
    }
    return next;
  }, [autonomousRuns, liveSnapshot]);

  const currentFixes = useMemo(
    () =>
      (liveSnapshot?.recent_transitions ?? []).filter(
        (item) => item.status === "running" || item.status === "queued",
      ).slice(0, 3),
    [liveSnapshot],
  );

  const globalOpen = liveSnapshot?.open_incidents ?? reporting.open_incidents;
  const hasRepair = (liveSnapshot?.repairing_incidents ?? 0) > 0;

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-12 pt-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <SdkBadge verification={sdkVerification} />
          {globalOpen > 0 && (
            <Link
              href="/incidents"
              className="flex items-center gap-1.5 rounded-full border border-[rgba(255,106,61,0.3)] bg-[rgba(255,106,61,0.12)] px-2.5 py-1 transition hover:bg-[rgba(255,106,61,0.2)]"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff6a3d] opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#ff6a3d]" />
              </span>
              <span className="text-[11px] font-semibold text-[#ffb99a]">
                {globalOpen} active incident{globalOpen !== 1 ? "s" : ""}
                {hasRepair ? " · repairing" : ""}
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
        <DashboardMetricCard
          label="Uptime"
          hint="% of days in the last 30d with no new incident"
          value={`${reporting.uptime_percent_last_30d.toFixed(1)}%`}
          delta={{ value: reporting.uptime_delta_pp, mode: "higherIsGood", format: "percent" }}
        />
        <DashboardMetricCard
          label="Avg response time"
          hint="Mean time from first signal to agent fix (autonomous), last 30d"
          value={
            reporting.avg_agent_response_seconds_last_30d == null
              ? "—"
              : formatMetricDurationSeconds(reporting.avg_agent_response_seconds_last_30d)
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
        <DashboardMetricCard
          label="Open incidents"
          hint="Currently open incidents"
          value={globalOpen === 0 ? "None" : String(globalOpen)}
          valueClassName={globalOpen === 0 ? "text-[#20c933]" : "text-[#ff6a3d]"}
        />
        <DashboardMetricCard
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

      {currentFixes.length > 0 ? (
        <div className="rounded-2xl border border-[rgba(45,127,249,0.2)] bg-[rgba(45,127,249,0.08)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[#93c5fd]">
                Currently fixing
              </p>
              <p className="mt-1 text-sm text-white/75">
                Live autonomous repair progress across active incidents.
              </p>
            </div>
            <span className="rounded-full border border-[rgba(45,127,249,0.3)] bg-[rgba(45,127,249,0.12)] px-2.5 py-1 text-[11px] font-semibold text-[#bfdbfe]">
              {liveSnapshot?.repairing_incidents ?? currentFixes.length} in flight
            </span>
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            {currentFixes.map((fix) => (
              <Link
                key={fix.run_id}
                href={`/incidents/${fix.incident_id}`}
                className="rounded-xl border border-white/[0.08] bg-black/20 px-4 py-3 transition hover:bg-white/[0.04]"
              >
                <p className="text-sm font-medium text-white/90">{fix.incident_title}</p>
                <p className="mt-1 text-xs uppercase tracking-wide text-[#93c5fd]">
                  {fix.status} · {fix.phase.replace(/_/g, " ")}
                </p>
                <p className="mt-2 line-clamp-2 text-sm text-white/55">
                  {fix.last_event ?? "Waiting for the next run event."}
                </p>
              </Link>
            ))}
          </div>
        </div>
      ) : null}

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

        <RecentIncidentsList
          incidents={incidents}
          autonomousRuns={mergedAutonomousRuns}
          viewAllHref="/incidents"
        />
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
  const labelFs = Math.max(14, Math.round(size * 0.09));
  const subFs = Math.max(9, Math.round(size * 0.042));
  const segments = data.reduce<Array<{ label: string; count: number; offset: number }>>(
    (acc, item) => {
      const previousOffset = acc.length > 0 ? acc[acc.length - 1]!.offset + (acc[acc.length - 1]!.count / total) * C : 0;
      acc.push({ label: item.label, count: item.count, offset: previousOffset });
      return acc;
    },
    [],
  );
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full max-h-[min(280px,42vh)] shrink-0" preserveAspectRatio="xMidYMid meet">
      {segments.map((segment, i) => {
        const dash = (segment.count / total) * C;
        return (
          <circle
            key={segment.label}
            cx={R}
            cy={R}
            r={r}
            fill="none"
            stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
            strokeWidth={SW}
            strokeDasharray={`${dash} ${C - dash}`}
            strokeDashoffset={-segment.offset}
            transform={`rotate(-90 ${R} ${R})`}
          />
        );
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

// ── Helpers ──

function Empty({ text }: { text: string }) {
  return <div className="flex h-40 items-center justify-center text-xs text-white/30">{text}</div>;
}

function filterByRange(incidents: IncidentSummary[], range: ChartRange): IncidentSummary[] {
  if (range === "all") return incidents;
  const cut = Date.now() - RANGE_MS[range];
  return incidents.filter((i) => new Date(i.last_seen_at).getTime() >= cut);
}

function buildTrendPoints(ri: IncidentSummary[], range: ChartRange) {
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
function fmtShort(ts: string) { return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date(ts)); }

import Link from "next/link";

import { ProjectSetupState } from "@/components/dashboard-ui";
import {
  AreaChart,
  EnvironmentStackedBar,
  IncidentHeatmap,
  METRICS_ACCENTS,
  MiniSparkline,
  RadialProgress,
  ServiceBars,
  SeverityDonut,
  UptimeGauge,
} from "@/components/metrics/metrics-charts";
import { MetricsToolbar } from "@/components/metrics/metrics-toolbar";
import {
  getHealthReadiness,
  getIncidentReportingOverview,
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
  getProjectOnboarding,
  getSuppressionSummary,
} from "@/lib/agent-platform";
import {
  buildActivitySeries,
  buildHeatmap,
  filterIncidentsByRange,
  formatDelta,
  formatPercent,
  formatSecondsShort,
  parseRange,
  RANGE_OPTIONS,
  type HeroDelta,
  type MetricsExportPayload,
  type RangeKey,
  type SeriesPoint,
} from "@/lib/metrics-series";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import type { SuppressionSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f59e0b",
  medium: "#8b5cf6",
  low: "#10b981",
};

const ENVIRONMENT_COLORS = [
  "#5b8dff",
  "#ff7a3d",
  "#ffb253",
  "#34d399",
  "#a78bfa",
  "#ef4444",
];

type MetricsPageProps = {
  searchParams: Promise<{ range?: string | string[] }>;
};

export default async function MetricsPage({
  searchParams,
}: MetricsPageProps) {
  const projectId = await resolvePrimaryProjectId();
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Metrics and reporting"
        title="Create a project before loading reporting views"
        description="Metrics are generated from project-scoped incident and runtime data. Complete onboarding first, then this route will populate with trend reporting and readiness summaries."
      />
    );
  }

  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Metrics and reporting"
        title="Finish onboarding before loading reporting views"
        description="Metrics and reporting remain in the onboarding-first state until the current project has a connected provider, synced repositories, secrets, and deployable service mappings."
      />
    );
  }

  const params = await searchParams;
  const rawRange = Array.isArray(params?.range) ? params.range[0] : params?.range;
  const range: RangeKey = parseRange(rawRange);

  const [incidentList, reporting, readiness, suppression] = await Promise.all([
    getIncidents({ projectId, limit: 100, offset: 0 }),
    getIncidentReportingOverview(projectId),
    getHealthReadiness().catch(() => null),
    getSuppressionSummary(projectId, { windowMinutes: 60 * 24 }).catch<SuppressionSummary | null>(
      () => null,
    ),
  ]);

  const allIncidents = incidentList.items;
  const incidentsInRange = filterIncidentsByRange(allIncidents, range);
  const activitySeries = buildActivitySeries(allIncidents, range);
  const heatmap = buildHeatmap(allIncidents);

  const latestRuns = await Promise.all(
    allIncidents.slice(0, 12).map(async (incident) => {
      try {
        const detail = await getLatestIncidentAutonomousRunDetail(incident.id);
        return detail.run;
      } catch {
        return null;
      }
    }),
  );

  const successfulRuns = latestRuns.filter((run) => run?.status === "succeeded").length;
  const activeRuns = latestRuns.filter(
    (run) => run && (run.status === "queued" || run.status === "running"),
  ).length;
  const failedRuns = latestRuns.filter((run) => run?.status === "failed").length;
  const autonomousSuccessPct =
    latestRuns.length > 0
      ? Math.round((successfulRuns / latestRuns.length) * 100)
      : 0;

  const severitySlices = reporting.severity_counts
    .filter((item) => item.count > 0)
    .map((item) => ({
      label: item.label,
      value: item.count,
      color: SEVERITY_COLORS[item.label] ?? "#a78bfa",
    }));
  const severityTotal = severitySlices.reduce((acc, s) => acc + s.value, 0);

  const environmentSegments = reporting.environment_counts
    .slice(0, 6)
    .map((item, index) => ({
      label: item.label,
      value: item.count,
      color: ENVIRONMENT_COLORS[index % ENVIRONMENT_COLORS.length],
    }));

  const services = reporting.service_counts.slice(0, 6);

  const exportPayload: MetricsExportPayload = {
    generated_at: new Date().toISOString(),
    project_id: projectId,
    range,
    reporting,
    suppression,
    incidents: allIncidents,
    activity_series: activitySeries,
  };

  const rangeLabel =
    RANGE_OPTIONS.find((option) => option.value === range)?.description ??
    "Last 7 days";

  const uptimeDelta = formatDelta(reporting.uptime_delta_pp, "pp");
  const responseDelta = formatDelta(reporting.avg_agent_response_delta_seconds, "s");
  const agentShareDelta = formatDelta(reporting.agent_resolution_delta_pp, "pp");
  const activitySubseries = activitySeries.slice(-14);

  const openRatePct =
    reporting.total_visible_incidents > 0
      ? Math.round(
          (reporting.open_incidents / reporting.total_visible_incidents) * 100,
        )
      : 0;

  return (
    <main className="mx-auto max-w-[1280px] space-y-12 px-4 pb-20 pt-6 text-white/90 sm:px-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-white/45">
            Metrics · {rangeLabel}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-[2.2rem]">
            Operational telemetry
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">
            Every signal we capture — incident pressure, autonomous throughput,
            severity mix, service hotspots, and noise filtering — composed into a
            single live view.
          </p>
        </div>
        <MetricsToolbar currentRange={range} exportPayload={exportPayload} />
      </section>

      <section className="grid grid-cols-2 gap-x-8 gap-y-10 lg:grid-cols-4">
        <HeroStat
          label="Visible incidents"
          value={String(reporting.total_visible_incidents)}
          caption={`${reporting.open_incidents} open · ${reporting.critical_incidents} critical`}
          series={activitySubseries}
          accent={METRICS_ACCENTS.orange.stroke}
        />
        <HeroStat
          label="Uptime (30d)"
          value={formatPercent(reporting.uptime_percent_last_30d, 2)}
          caption="Calendar days without new incidents"
          delta={uptimeDelta}
          deltaUp="good"
          accent={METRICS_ACCENTS.emerald.stroke}
        />
        <HeroStat
          label="Agent response"
          value={formatSecondsShort(reporting.avg_agent_response_seconds_last_30d)}
          caption="Mean signal → autonomous resolution"
          delta={responseDelta}
          deltaUp="bad"
          accent={METRICS_ACCENTS.blue.stroke}
        />
        <HeroStat
          label="Agent-resolved share"
          value={formatPercent(reporting.agent_resolution_percent_last_30d, 0)}
          caption="Share of resolutions driven autonomously"
          delta={agentShareDelta}
          deltaUp="good"
          accent={METRICS_ACCENTS.violet.stroke}
        />
      </section>

      <section className="space-y-5">
        <SectionHeader
          eyebrow="Incident volume"
          title="Signal pressure"
          description={`Rolling incident activity bucketed for the selected window. ${incidentsInRange.length} incident${
            incidentsInRange.length === 1 ? "" : "s"
          } in range · ${reporting.total_event_volume} total events ingested.`}
        />
        <div className="relative overflow-hidden rounded-2xl border border-white/[0.06] bg-[linear-gradient(180deg,rgba(255,255,255,0.02),rgba(255,255,255,0))] px-3 pb-2 pt-5 sm:px-5">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,122,61,0.35),transparent)]" />
          <AreaChart
            series={activitySeries}
            gradientId="metrics-activity"
            accent="orange"
            height={240}
          />
        </div>
      </section>

      <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="space-y-4">
          <SectionHeader
            eyebrow="Reliability"
            title="Uptime"
            compact
          />
          <UptimeGauge value={reporting.uptime_percent_last_30d} />
          <p className="text-[12px] leading-5 text-white/55">
            {reporting.uptime_delta_pp >= 0
              ? `Up ${reporting.uptime_delta_pp.toFixed(1)}pp versus the previous 30 days.`
              : `Down ${Math.abs(reporting.uptime_delta_pp).toFixed(1)}pp versus the previous 30 days.`}
          </p>
        </div>

        <div className="space-y-4">
          <SectionHeader
            eyebrow="Severity"
            title="Incident mix"
            compact
          />
          {severityTotal > 0 ? (
            <SeverityDonut
              slices={severitySlices}
              total={reporting.total_visible_incidents}
              totalLabel="Incidents"
            />
          ) : (
            <EmptyState message="No visible incidents to categorize by severity." />
          )}
        </div>

        <div className="space-y-4">
          <SectionHeader
            eyebrow="Environments"
            title="Where the signal lives"
            compact
          />
          {environmentSegments.length > 0 ? (
            <EnvironmentStackedBar segments={environmentSegments} />
          ) : (
            <EmptyState message="No environment metadata on current incidents." />
          )}
        </div>
      </section>

      <section className="grid gap-8 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <SectionHeader
            eyebrow="Service concentration"
            title="Where pressure is concentrated"
            description="Top services by incident count. Higher bars mean repeated incident exposure."
          />
          <ServiceBars items={services} />
        </div>

        <div className="space-y-5">
          <SectionHeader
            eyebrow="Incident heat"
            title="Weekday × hour of day"
            description="Last 7 days of incidents plotted by when they last fired, UTC-local."
          />
          <IncidentHeatmap
            days={heatmap.days}
            hours={heatmap.hours}
            matrix={heatmap.matrix}
            max={heatmap.max}
          />
          <HeatmapLegend max={heatmap.max} />
        </div>
      </section>

      <section className="space-y-5">
        <SectionHeader
          eyebrow="Autonomy"
          title="Agent throughput"
          description="Sampled across the most recent 12 incidents — how the autonomous agent is clearing the queue."
        />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <RadialProgress
            value={autonomousSuccessPct}
            label="Autonomous success"
            accent="#34d399"
            caption={`${successfulRuns} of ${latestRuns.length} sampled runs succeeded`}
          />
          <MiniStatInline
            label="In-flight runs"
            value={String(activeRuns)}
            caption="Queued or running agents"
            dotColor="#5b8dff"
          />
          <MiniStatInline
            label="Failed runs"
            value={String(failedRuns)}
            caption="Need manual attention"
            dotColor={failedRuns > 0 ? "#ef4444" : "#4b5563"}
          />
          <MiniStatInline
            label="Backend readiness"
            value={readiness?.checks.database.ready ? "Healthy" : "Degraded"}
            caption={
              readiness?.checks.database.configured
                ? "Database check passing"
                : "Readiness probe unavailable"
            }
            dotColor={readiness?.checks.database.ready ? "#34d399" : "#f59e0b"}
          />
        </div>
      </section>

      <section className="space-y-5">
        <SectionHeader
          eyebrow="Noise filter"
          title="Suppressed telemetry"
          description="What the classifier held back so the incident queue can stay high-signal. Numbers cover the last 24 hours."
          aside={
            <Link
              href={`/incidents/noise?project_id=${encodeURIComponent(projectId)}`}
              className="text-[12px] font-semibold text-white/70 transition hover:text-white"
            >
              Open noise review →
            </Link>
          }
        />
        <SuppressionRail summary={suppression} />
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] pt-6 text-[11px] text-white/40">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="h-1.5 w-1.5 rounded-full bg-[linear-gradient(135deg,#ff7a3d,#ff5a2a)]"
          />
          Snapshot updates on navigation. Use export to archive current state.
        </div>
        <div className="flex items-center gap-4">
          <span>Project {projectId.slice(0, 8)}…</span>
          <span>Open-rate {openRatePct}%</span>
          <span>
            Updated{" "}
            {new Date().toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
      </section>
    </main>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  compact,
  aside,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  compact?: boolean;
  aside?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/40">
          {eyebrow}
        </p>
        <h2
          className={`mt-1 font-semibold tracking-tight text-white ${
            compact ? "text-[1.1rem]" : "text-[1.35rem]"
          }`}
        >
          {title}
        </h2>
        {description ? (
          <p className="mt-1 max-w-2xl text-[13px] leading-5 text-white/55">
            {description}
          </p>
        ) : null}
      </div>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </div>
  );
}

function HeroStat({
  label,
  value,
  caption,
  delta,
  deltaUp,
  series,
  accent = "#ff7a3d",
}: {
  label: string;
  value: string;
  caption?: string;
  delta?: HeroDelta;
  deltaUp?: "good" | "bad";
  series?: SeriesPoint[];
  accent?: string;
}) {
  const toneClass = (() => {
    if (!delta || delta.direction === "flat") {
      return "text-white/55";
    }
    const isUp = delta.direction === "up";
    const polarity = deltaUp === "bad" ? !isUp : isUp;
    return polarity ? "text-emerald-300" : "text-rose-300";
  })();
  const arrow = delta
    ? delta.direction === "up"
      ? "↑"
      : delta.direction === "down"
        ? "↓"
        : "→"
    : null;
  return (
    <div className="relative flex flex-col gap-2 border-l border-white/[0.07] pl-5 first:border-l-0 first:pl-0">
      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">
        {label}
      </p>
      <div className="flex items-baseline gap-3">
        <p className="text-[2rem] font-semibold leading-none text-white sm:text-[2.3rem]">
          {value}
        </p>
        {delta ? (
          <span className={`text-[12px] font-semibold ${toneClass}`}>
            {arrow} {delta.magnitude}
          </span>
        ) : null}
      </div>
      {caption ? (
        <p className="text-[12px] leading-5 text-white/50">{caption}</p>
      ) : null}
      {series && series.length > 0 ? (
        <div className="mt-1">
          <MiniSparkline series={series} accent={accent} />
        </div>
      ) : null}
    </div>
  );
}

function MiniStatInline({
  label,
  value,
  caption,
  dotColor,
}: {
  label: string;
  value: string;
  caption?: string;
  dotColor: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="h-2 w-2 rounded-full"
          style={{ background: dotColor, boxShadow: `0 0 12px ${dotColor}55` }}
        />
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">
          {label}
        </p>
      </div>
      <p className="text-2xl font-semibold text-white">{value}</p>
      {caption ? (
        <p className="text-[12px] leading-5 text-white/50">{caption}</p>
      ) : null}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-white/[0.08] bg-white/[0.015] px-4 py-6 text-[12px] text-white/45">
      {message}
    </div>
  );
}

function HeatmapLegend({ max }: { max: number }) {
  const steps = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div className="flex items-center gap-3 text-[11px] text-white/45">
      <span>Low</span>
      <div className="flex h-2.5 overflow-hidden rounded-full">
        {steps.map((step) => (
          <span
            key={step}
            className="h-full w-6"
            style={{
              background:
                step === 0
                  ? "rgba(255,255,255,0.04)"
                  : `rgba(255, 122, 61, ${(0.15 + step * 0.75).toFixed(2)})`,
            }}
          />
        ))}
      </div>
      <span>High{max > 0 ? ` · ${max}/hr` : ""}</span>
    </div>
  );
}

function SuppressionRail({ summary }: { summary: SuppressionSummary | null }) {
  if (!summary) {
    return (
      <EmptyState message="Suppression summary is unavailable right now." />
    );
  }

  const userErrors = summary.user_error_event_count;
  const ambiguous = summary.code_ambiguous_event_count;
  const total = userErrors + ambiguous;

  const cards: {
    label: string;
    value: string;
    caption: string;
    color: string;
  }[] = [
    {
      label: "User-error events",
      value: String(userErrors),
      caption: `${summary.user_error_unique_fingerprints} unique fingerprints`,
      color: "#a78bfa",
    },
    {
      label: "Ambiguous events",
      value: String(ambiguous),
      caption: `${summary.code_ambiguous_unique_fingerprints} unique fingerprints`,
      color: "#ffb253",
    },
    {
      label: "Total suppressed",
      value: String(total),
      caption: "Held back from the incident pipeline",
      color: "#5b8dff",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-5 sm:grid-cols-3">
        {cards.map((card) => (
          <div key={card.label} className="flex items-center gap-4">
            <span
              aria-hidden
              className="h-10 w-1.5 rounded-full"
              style={{ background: card.color, boxShadow: `0 0 14px ${card.color}55` }}
            />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">
                {card.label}
              </p>
              <p className="mt-1 text-[1.6rem] font-semibold leading-none text-white">
                {card.value}
              </p>
              <p className="mt-1 text-[12px] leading-5 text-white/50">{card.caption}</p>
            </div>
          </div>
        ))}
      </div>
      {total > 0 ? (
        <div className="relative h-2 overflow-hidden rounded-full bg-white/[0.04]">
          <div className="absolute inset-0 flex">
            <span
              className="h-full"
              style={{
                width: `${(userErrors / total) * 100}%`,
                background: "linear-gradient(90deg,#a78bfa,#8b5cf6)",
              }}
            />
            <span
              className="h-full"
              style={{
                width: `${(ambiguous / total) * 100}%`,
                background: "linear-gradient(90deg,#ffb253,#ff7a3d)",
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

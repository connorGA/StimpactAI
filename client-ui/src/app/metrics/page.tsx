import { PageHeader, PreviewNotice } from "@/components/dashboard-ui";
import { getIncidents } from "@/lib/agent-platform";
import {
  buildIncidentTrendSeries,
  buildLatencySeries,
  buildUptimeSeries,
  calculateLinePath,
  calculateUptimePreview,
  countOpenIncidents,
  getEnvironmentBreakdown,
  getSeverityBreakdown,
  getTopServices,
  totalEventVolume,
} from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export default async function MetricsPage() {
  const incidentList = await getIncidents({ limit: 100, offset: 0 });
  const incidents = incidentList.items;
  const uptimeSeries = buildUptimeSeries(incidents);
  const volumeSeries = buildIncidentTrendSeries(incidents);
  const latencySeries = buildLatencySeries(incidents);
  const severity = getSeverityBreakdown(incidents);
  const services = getTopServices(incidents, 5);
  const environments = getEnvironmentBreakdown(incidents, 4);
  const uptimePath = calculateLinePath(uptimeSeries, 180, 540);
  const volumePath = calculateLinePath(volumeSeries, 180, 540);
  const maxServiceCount = Math.max(...services.map((item) => item.count), 1);

  return (
    <main className="space-y-8">
      <PageHeader
        eyebrow="Metrics and reporting"
        title="Reliability reporting built around trend reading and operational signal"
        description="The metrics route is now a reporting surface first: darker data stage up top, neutral analytical sheets below, and less repeated boxed chrome."
      />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <section className="ops-sheet-dark rounded-[28px] p-7">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">
                Uptime trend
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Seven-day reliability</h2>
              <p className="mt-2 text-sm leading-6 text-white/70">
                A high-signal view of stability before the user drills into more
                detailed reporting modules.
              </p>
            </div>
            <div className="ops-dark-block rounded-[18px] px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">
                Current uptime
              </p>
              <p className="mt-2 text-3xl font-semibold">
                {calculateUptimePreview(incidents)}
              </p>
            </div>
          </div>

          <div className="ops-grid-chart mt-6 rounded-[22px] border border-white/10 bg-black/10 px-4 py-4">
            <svg viewBox="0 0 540 180" className="h-64 w-full">
              <path
                d={uptimePath}
                fill="none"
                stroke="url(#metricsUptime)"
                strokeWidth="5"
                strokeLinecap="round"
              />
              <defs>
                <linearGradient id="metricsUptime" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#ffb253" />
                  <stop offset="100%" stopColor="#ff5a2a" />
                </linearGradient>
              </defs>
            </svg>
            <div className="mt-4 grid grid-cols-7 text-xs text-white/48">
              {uptimeSeries.map((point) => (
                <span key={point.label}>{point.label}</span>
              ))}
            </div>
          </div>
        </section>

        <div className="space-y-6">
          <DonutPanel
            title="Incident mix"
            value={incidentList.total}
            detail="Visible incidents contributing to the current metrics sample."
          />

          <div className="ops-sheet-muted rounded-[28px] p-6">
            <p className="ops-kicker text-[11px] font-semibold uppercase">Snapshot</p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <MetricTile
              label="Open rate"
              value={`${Math.round((countOpenIncidents(incidents) / Math.max(incidents.length, 1)) * 100)}%`}
            />
            <MetricTile
              label="Event volume"
              value={String(totalEventVolume(incidents))}
            />
            <MetricTile
              label="Services"
              value={String(services.length)}
            />
            <MetricTile
              label="Environments"
              value={String(environments.length)}
            />
          </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <ChartPanel
          title="Incident volume"
          description="Short-horizon issue volume trend."
        >
          <div className="ops-grid-chart rounded-[20px] bg-white/44 px-4 py-4">
            <svg viewBox="0 0 540 180" className="h-56 w-full">
              <path
                d={volumePath}
                fill="none"
                stroke="url(#metricsVolume)"
                strokeWidth="5"
                strokeLinecap="round"
              />
              <defs>
                <linearGradient id="metricsVolume" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#4b6bfb" />
                  <stop offset="100%" stopColor="#3451d1" />
                </linearGradient>
              </defs>
            </svg>
            <div className="mt-4 grid grid-cols-6 text-xs text-[#98a2b3]">
              {volumeSeries.map((point) => (
                <span key={point.label}>{point.label}</span>
              ))}
            </div>
          </div>
        </ChartPanel>

        <ChartPanel
          title="Latency profile"
          description="Representative latency bands across major platform areas."
        >
          <div className="space-y-4">
            {latencySeries.map((item) => (
              <div key={item.label}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-[#111827]">{item.label}</span>
                  <span className="text-[#667085]">{item.value} ms</span>
                </div>
                <div className="vault-bar-track h-3 rounded-full">
                  <div
                    className="h-3 rounded-full bg-[linear-gradient(90deg,#4b6bfb,#3451d1)]"
                    style={{ width: `${Math.min(item.value / 4, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </ChartPanel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)_360px]">
        <ChartPanel
          title="Service concentration"
          description="Which services are contributing the most incident pressure."
        >
          <div className="space-y-4">
            {services.map((item) => (
              <div key={item.label}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-[#111827]">{item.label}</span>
                  <span className="text-[#667085]">{item.count} incidents</span>
                </div>
                <div className="vault-bar-track h-3 rounded-full">
                  <div
                    className="h-3 rounded-full bg-[linear-gradient(90deg,#ff8b68,#ff5a2a)]"
                    style={{ width: `${Math.max(12, Math.round((item.count / maxServiceCount) * 100))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </ChartPanel>

        <ChartPanel
          title="Severity split"
          description="Current severity breakdown for the visible incident sample."
        >
          <div className="space-y-4">
            {severity.map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-[18px] bg-white/44 px-4 py-4">
                <span className="text-sm font-medium capitalize text-[#111827]">
                  {item.label}
                </span>
                <span className="text-sm text-[#667085]">{item.count}</span>
              </div>
            ))}
          </div>
        </ChartPanel>

        <PreviewNotice
          title="Metrics still awaiting backend wiring"
          items={[
            "Historical MTTA, MTTR, error-budget burn, and deploy overlays are not connected yet.",
            "Scheduled reports and exports are product placeholders for now.",
            "These visual graphs are ready for time-series data once those APIs exist.",
          ]}
        />
      </section>
    </main>
  );
}

function ChartPanel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="ops-sheet rounded-[26px] p-6">
      <p className="ops-kicker text-[11px] font-semibold uppercase">
        Analytics module
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-[#111827]">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[#667085]">{description}</p>
      <div className="mt-5 border-t border-[rgba(24,24,27,0.08)] pt-5">{children}</div>
    </section>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l border-[rgba(24,24,27,0.08)] pl-4 first:border-l-0 first:pl-0">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
        {label}
      </p>
      <p className="mt-3 text-3xl font-semibold text-[#111827]">{value}</p>
    </div>
  );
}

function DonutPanel({
  title,
  value,
  detail,
}: {
  title: string;
  value: number;
  detail: string;
}) {
  return (
    <section className="ops-sheet rounded-[26px] p-6">
      <p className="ops-kicker text-[11px] font-semibold uppercase">
        Visual summary
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-[#111827]">{title}</h2>
      <div className="mt-6 flex items-center justify-center">
        <div className="relative h-52 w-52 rounded-full bg-[conic-gradient(#ff5a2a_0_32%,#4b6bfb_32%_68%,#ffb253_68%_100%)] p-6">
          <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-[#faf6ef] text-center">
            <p className="text-4xl font-semibold text-[#111827]">{value}</p>
            <p className="mt-1 text-sm text-[#667085]">visible incidents</p>
          </div>
        </div>
      </div>
      <p className="mt-5 text-sm leading-6 text-[#667085]">{detail}</p>
    </section>
  );
}

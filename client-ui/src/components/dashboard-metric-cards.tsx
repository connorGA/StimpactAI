type MetricDelta = {
  value: number;
  mode: "higherIsGood" | "lowerIsGood";
  format: "percent" | "seconds";
};

type DashboardMetricCardProps = {
  label: string;
  hint?: string;
  value: string;
  valueClassName?: string;
  delta?: MetricDelta | null;
};

export function DashboardMetricCard({
  label,
  hint,
  value,
  valueClassName,
  delta,
}: DashboardMetricCardProps) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[rgba(14,18,28,0.8)] px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <p
          className="min-w-0 flex-1 text-[11px] font-medium uppercase tracking-wider text-white/40"
          title={hint}
        >
          {label}
        </p>
        {delta ? (
          <div className="shrink-0">
            <MetricDeltaBadge delta={delta} />
          </div>
        ) : null}
      </div>
      <p className={`mt-1.5 text-2xl font-bold tabular-nums ${valueClassName ?? "text-white"}`}>
        {value}
      </p>
    </div>
  );
}

function MetricDeltaBadge({ delta }: { delta: MetricDelta }) {
  const { value: raw, mode, format } = delta;
  if (Number.isNaN(raw)) return null;

  const good =
    raw === 0 ? null : mode === "higherIsGood" ? raw > 0 : raw < 0;
  const up = raw > 0;

  const text =
    format === "percent"
      ? `${Math.abs(raw).toFixed(1)}%`
      : formatAbsDurationSeconds(Math.abs(raw));

  const base =
    "inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums leading-none";
  if (raw === 0) {
    return (
      <span
        className={`${base} border-white/10 bg-white/[0.06] text-white/45`}
        title="Change vs prior 30 days"
      >
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

export function formatMetricDurationSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function formatAbsDurationSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

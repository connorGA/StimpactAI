import type { SeriesPoint } from "@/lib/metrics-series";

type Accent = {
  stroke: string;
  fill1: string;
  fill2: string;
  dot: string;
};

export const METRICS_ACCENTS: Record<string, Accent> = {
  orange: {
    stroke: "#ff7a3d",
    fill1: "rgba(255, 122, 61, 0.42)",
    fill2: "rgba(255, 122, 61, 0.02)",
    dot: "#ffb253",
  },
  blue: {
    stroke: "#5b8dff",
    fill1: "rgba(91, 141, 255, 0.38)",
    fill2: "rgba(91, 141, 255, 0.02)",
    dot: "#8bb3ff",
  },
  emerald: {
    stroke: "#34d399",
    fill1: "rgba(52, 211, 153, 0.35)",
    fill2: "rgba(52, 211, 153, 0.02)",
    dot: "#6ee7b7",
  },
  violet: {
    stroke: "#a78bfa",
    fill1: "rgba(167, 139, 250, 0.38)",
    fill2: "rgba(167, 139, 250, 0.02)",
    dot: "#c4b5fd",
  },
};

function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    return `M ${points[0].x} ${points[0].y}`;
  }
  const segments: string[] = [
    `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`,
  ];
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    segments.push(
      `C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)} ${cp2x.toFixed(2)} ${cp2y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`,
    );
  }
  return segments.join(" ");
}

type AreaChartProps = {
  series: SeriesPoint[];
  accent?: keyof typeof METRICS_ACCENTS;
  gradientId: string;
  height?: number;
  axisEveryN?: number;
  className?: string;
};

export function AreaChart({
  series,
  accent = "orange",
  gradientId,
  height = 220,
  axisEveryN,
  className = "h-64 w-full",
}: AreaChartProps) {
  const width = 900;
  const marginTop = 18;
  const marginBottom = 30;
  const marginLeft = 40;
  const marginRight = 14;
  const innerWidth = width - marginLeft - marginRight;
  const innerHeight = height - marginTop - marginBottom;
  const accentColors = METRICS_ACCENTS[accent] ?? METRICS_ACCENTS.orange;

  const maxValue = Math.max(1, ...series.map((point) => point.value));
  const stepX = innerWidth / Math.max(series.length - 1, 1);

  const points = series.map((point, index) => ({
    x: marginLeft + index * stepX,
    y: marginTop + innerHeight - (point.value / maxValue) * innerHeight,
    value: point.value,
    label: point.label,
  }));

  const linePath = smoothPath(points);
  const lastX = points[points.length - 1]?.x ?? marginLeft;
  const firstX = points[0]?.x ?? marginLeft;
  const baselineY = marginTop + innerHeight;
  const areaPath =
    points.length > 0
      ? `${linePath} L ${lastX.toFixed(2)} ${baselineY.toFixed(2)} L ${firstX.toFixed(2)} ${baselineY.toFixed(2)} Z`
      : "";

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => ({
    y: marginTop + innerHeight * (1 - t),
    value: Math.round(maxValue * t),
  }));

  const targetLabelCount = 7;
  const everyN =
    axisEveryN ??
    Math.max(1, Math.ceil(points.length / targetLabelCount));
  const labelIndices = points
    .map((_, i) => i)
    .filter((i) => i === 0 || i === points.length - 1 || i % everyN === 0);

  const peak = points.reduce(
    (best, point) =>
      point.value > best.value ? { value: point.value, index: points.indexOf(point) } : best,
    { value: -Infinity, index: -1 },
  );

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      role="img"
      aria-label="Incident activity over time"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accentColors.fill1} />
          <stop offset="100%" stopColor={accentColors.fill2} />
        </linearGradient>
        <linearGradient id={`${gradientId}-line`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={accentColors.stroke} stopOpacity="0.75" />
          <stop offset="100%" stopColor={accentColors.stroke} stopOpacity="1" />
        </linearGradient>
      </defs>

      {yTicks.map((tick) => (
        <line
          key={`grid-${tick.y}`}
          x1={marginLeft}
          x2={width - marginRight}
          y1={tick.y}
          y2={tick.y}
          stroke="rgba(255,255,255,0.06)"
          strokeDasharray="2 4"
        />
      ))}

      {areaPath ? <path d={areaPath} fill={`url(#${gradientId})`} /> : null}
      {linePath ? (
        <path
          d={linePath}
          fill="none"
          stroke={`url(#${gradientId}-line)`}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : null}

      {points.map((point, index) =>
        point.value > 0 && (index === peak.index || index === points.length - 1) ? (
          <g key={`dot-${index}`}>
            <circle
              cx={point.x}
              cy={point.y}
              r="5"
              fill={accentColors.stroke}
              opacity="0.2"
            />
            <circle
              cx={point.x}
              cy={point.y}
              r="2.75"
              fill={accentColors.stroke}
            />
          </g>
        ) : null,
      )}

      {peak.index >= 0 && points[peak.index] && peak.value > 0 ? (
        <g>
          <rect
            x={Math.min(
              points[peak.index].x + 8,
              width - marginRight - 58,
            )}
            y={points[peak.index].y - 24}
            width="50"
            height="18"
            rx="5"
            fill="rgba(10,14,24,0.9)"
            stroke={accentColors.stroke}
            strokeOpacity="0.25"
          />
          <text
            x={Math.min(points[peak.index].x + 33, width - marginRight - 33)}
            y={points[peak.index].y - 11}
            textAnchor="middle"
            className="fill-white text-[11px] font-semibold"
          >
            {peak.value}
          </text>
        </g>
      ) : null}

      {yTicks.map((tick) => (
        <text
          key={`y-label-${tick.y}`}
          x={marginLeft - 8}
          y={tick.y + 3}
          textAnchor="end"
          className="fill-white/35 text-[10px]"
        >
          {tick.value}
        </text>
      ))}

      {labelIndices.map((index) => {
        const point = points[index];
        if (!point) return null;
        return (
          <text
            key={`x-label-${index}`}
            x={point.x}
            y={height - 10}
            textAnchor="middle"
            className="fill-white/45 text-[10px]"
          >
            {point.label}
          </text>
        );
      })}
    </svg>
  );
}

type UptimeGaugeProps = {
  value: number;
  label?: string;
};

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const angle = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polarToCartesian(cx, cy, r, startDeg);
  const end = polarToCartesian(cx, cy, r, endDeg);
  const sweepAngle = endDeg - startDeg;
  const largeArc = sweepAngle <= 180 ? 0 : 1;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

export function UptimeGauge({ value, label = "Uptime (30d)" }: UptimeGaugeProps) {
  const cx = 110;
  const cy = 108;
  const radius = 80;
  const startDeg = 135;
  const endDeg = 405;
  const safeValue = Math.max(0, Math.min(100, value));
  const sweep = startDeg + ((endDeg - startDeg) * safeValue) / 100;
  const bgPath = arcPath(cx, cy, radius, startDeg, endDeg);
  const fgPath = arcPath(cx, cy, radius, startDeg, sweep);

  const tone =
    safeValue >= 99
      ? { start: "#34d399", end: "#10b981" }
      : safeValue >= 95
        ? { start: "#ffb253", end: "#ff7a3d" }
        : { start: "#ff6a3d", end: "#ef4444" };

  return (
    <svg viewBox="0 0 220 200" className="h-44 w-full" role="img" aria-label={label}>
      <defs>
        <linearGradient id="metrics-gauge-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={tone.start} />
          <stop offset="100%" stopColor={tone.end} />
        </linearGradient>
      </defs>
      <path
        d={bgPath}
        stroke="rgba(255,255,255,0.06)"
        strokeWidth="14"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d={fgPath}
        stroke="url(#metrics-gauge-grad)"
        strokeWidth="14"
        fill="none"
        strokeLinecap="round"
      />
      <text
        x={cx}
        y={cy + 2}
        textAnchor="middle"
        className="fill-white text-[38px] font-semibold"
      >
        {safeValue.toFixed(1)}
        <tspan className="fill-white/55 text-[20px] font-medium">%</tspan>
      </text>
      <text
        x={cx}
        y={cy + 26}
        textAnchor="middle"
        className="fill-white/50 text-[10px] uppercase tracking-[0.2em]"
      >
        {label}
      </text>
    </svg>
  );
}

type DonutSlice = {
  label: string;
  value: number;
  color: string;
};

type SeverityDonutProps = {
  slices: DonutSlice[];
  total: number;
  totalLabel: string;
};

export function SeverityDonut({
  slices,
  total,
  totalLabel,
}: SeverityDonutProps) {
  const cx = 110;
  const cy = 110;
  const radius = 82;
  const strokeWidth = 22;
  const circumference = 2 * Math.PI * radius;

  const sumValues = slices.reduce((acc, slice) => acc + slice.value, 0);
  let offset = 0;

  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 220 220" className="h-44 w-44" role="img" aria-label="Severity distribution">
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
          fill="none"
        />
        {sumValues > 0
          ? slices.map((slice) => {
              if (slice.value <= 0) return null;
              const fraction = slice.value / sumValues;
              const length = fraction * circumference;
              const dashoffset = circumference - offset;
              const element = (
                <circle
                  key={slice.label}
                  cx={cx}
                  cy={cy}
                  r={radius}
                  stroke={slice.color}
                  strokeWidth={strokeWidth}
                  fill="none"
                  strokeDasharray={`${length} ${circumference}`}
                  strokeDashoffset={dashoffset}
                  transform={`rotate(-90 ${cx} ${cy})`}
                  strokeLinecap="butt"
                />
              );
              offset += length;
              return element;
            })
          : null}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          className="fill-white text-[34px] font-semibold"
        >
          {total}
        </text>
        <text
          x={cx}
          y={cy + 20}
          textAnchor="middle"
          className="fill-white/45 text-[10px] uppercase tracking-[0.2em]"
        >
          {totalLabel}
        </text>
      </svg>
      <ul className="space-y-2 text-[13px]">
        {slices.map((slice) => (
          <li key={slice.label} className="flex items-center gap-3">
            <span
              aria-hidden
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: slice.color }}
            />
            <span className="min-w-[68px] capitalize text-white/70">{slice.label}</span>
            <span className="font-semibold text-white">{slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type StackedBarSegment = {
  label: string;
  value: number;
  color: string;
};

export function EnvironmentStackedBar({
  segments,
}: {
  segments: StackedBarSegment[];
}) {
  const total = segments.reduce((acc, segment) => acc + segment.value, 0);
  const safeTotal = Math.max(total, 1);
  return (
    <div className="space-y-4">
      <div className="relative h-3 w-full overflow-hidden rounded-full bg-white/[0.05]">
        <div className="absolute inset-0 flex">
          {segments.map((segment) => {
            const width = (segment.value / safeTotal) * 100;
            if (width <= 0) return null;
            return (
              <div
                key={segment.label}
                style={{ width: `${width}%`, background: segment.color }}
                className="h-full"
                title={`${segment.label}: ${segment.value}`}
              />
            );
          })}
        </div>
      </div>
      <ul className="grid gap-2 text-[12px] sm:grid-cols-2">
        {segments.map((segment) => {
          const pct = Math.round((segment.value / safeTotal) * 100);
          return (
            <li
              key={segment.label}
              className="flex items-center gap-3 text-white/75"
            >
              <span
                aria-hidden
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: segment.color }}
              />
              <span className="truncate text-white/85">{segment.label}</span>
              <span className="ml-auto text-white/50">
                {segment.value}
                <span className="ml-1 text-white/35">·</span>
                <span className="ml-1 font-semibold text-white/70">{pct}%</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

type ServiceBarsProps = {
  items: { label: string; count: number }[];
  accent?: string;
};

export function ServiceBars({ items, accent = "#ff7a3d" }: ServiceBarsProps) {
  const max = Math.max(1, ...items.map((item) => item.count));
  if (items.length === 0) {
    return (
      <p className="text-sm text-white/45">
        No services are contributing incidents in this window.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const pct = (item.count / max) * 100;
        return (
          <li key={item.label} className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3 text-[12px]">
              <span className="min-w-0 truncate font-medium text-white/85">
                {item.label}
              </span>
              <span className="text-white/55">
                <span className="font-semibold text-white/85">{item.count}</span>{" "}
                <span className="text-[11px]">incidents</span>
              </span>
            </div>
            <div className="relative h-2 overflow-hidden rounded-full bg-white/[0.04]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(3, pct)}%`,
                  background: `linear-gradient(90deg, ${accent}, rgba(255,122,61,0.55))`,
                  boxShadow: "0 0 10px rgba(255,122,61,0.18)",
                }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function IncidentHeatmap({
  days,
  hours,
  matrix,
  max,
}: {
  days: string[];
  hours: number[];
  matrix: number[][];
  max: number;
}) {
  const cellWidth = 22;
  const cellHeight = 22;
  const gap = 3;
  const labelGutter = 36;
  const bottomLabels = 22;
  const totalWidth = labelGutter + hours.length * (cellWidth + gap);
  const totalHeight = days.length * (cellHeight + gap) + bottomLabels;

  const scale = (value: number) => {
    if (value <= 0) return "rgba(255,255,255,0.03)";
    const normalized = Math.min(1, value / Math.max(max, 1));
    const alpha = 0.15 + normalized * 0.75;
    return `rgba(255, 122, 61, ${alpha.toFixed(3)})`;
  };

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${totalWidth} ${totalHeight}`}
        className="h-[190px] w-full min-w-[560px]"
        role="img"
        aria-label="Incident heatmap (last 7 days by hour of day)"
      >
        {days.map((day, rowIndex) => (
          <text
            key={`day-${day}-${rowIndex}`}
            x={labelGutter - 10}
            y={rowIndex * (cellHeight + gap) + cellHeight / 2 + 4}
            textAnchor="end"
            className="fill-white/45 text-[10px] uppercase"
          >
            {day}
          </text>
        ))}
        {matrix.map((row, rowIndex) =>
          row.map((value, colIndex) => (
            <rect
              key={`cell-${rowIndex}-${colIndex}`}
              x={labelGutter + colIndex * (cellWidth + gap)}
              y={rowIndex * (cellHeight + gap)}
              width={cellWidth}
              height={cellHeight}
              rx="4"
              fill={scale(value)}
              stroke="rgba(255,255,255,0.04)"
            >
              <title>{`${days[rowIndex]} ${String(colIndex).padStart(2, "0")}:00 — ${value} incident${value === 1 ? "" : "s"}`}</title>
            </rect>
          )),
        )}
        {hours
          .filter((hour) => hour % 4 === 0)
          .map((hour) => (
            <text
              key={`hour-${hour}`}
              x={labelGutter + hour * (cellWidth + gap) + cellWidth / 2}
              y={days.length * (cellHeight + gap) + 14}
              textAnchor="middle"
              className="fill-white/40 text-[10px]"
            >
              {String(hour).padStart(2, "0")}
            </text>
          ))}
      </svg>
    </div>
  );
}

export function MiniSparkline({
  series,
  accent = "#ff7a3d",
  width = 120,
  height = 34,
}: {
  series: SeriesPoint[];
  accent?: string;
  width?: number;
  height?: number;
}) {
  if (series.length === 0) {
    return null;
  }
  const max = Math.max(1, ...series.map((p) => p.value));
  const stepX = width / Math.max(series.length - 1, 1);
  const points = series.map((point, index) => ({
    x: index * stepX,
    y: height - (point.value / max) * height,
  }));
  const pathD = smoothPath(points);
  const uniqueId = `mini-${Math.random().toString(36).slice(2)}`;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-[34px] w-full"
      aria-hidden
    >
      <defs>
        <linearGradient id={uniqueId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.35" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={`${pathD} L ${points[points.length - 1].x} ${height} L 0 ${height} Z`}
        fill={`url(#${uniqueId})`}
      />
      <path
        d={pathD}
        fill="none"
        stroke={accent}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function RadialProgress({
  value,
  label,
  accent = "#5b8dff",
  caption,
}: {
  value: number;
  label: string;
  accent?: string;
  caption?: string;
}) {
  const safe = Math.max(0, Math.min(100, value));
  const radius = 44;
  const stroke = 8;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (safe / 100) * circumference;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 120 120" className="h-[108px] w-[108px]" role="img" aria-label={label}>
        <circle
          cx="60"
          cy="60"
          r={radius}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          cx="60"
          cy="60"
          r={radius}
          stroke={accent}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 60 60)"
        />
        <text
          x="60"
          y="64"
          textAnchor="middle"
          className="fill-white text-[22px] font-semibold"
        >
          {safe.toFixed(0)}%
        </text>
      </svg>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">
          {label}
        </p>
        {caption ? (
          <p className="mt-1 text-[12px] text-white/60">{caption}</p>
        ) : null}
      </div>
    </div>
  );
}

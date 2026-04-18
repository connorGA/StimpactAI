import type {
  IncidentReportingOverview,
  IncidentSummary,
  SuppressionSummary,
} from "@/lib/types";

export type RangeKey = "1h" | "24h" | "7d" | "30d";

export const DEFAULT_RANGE: RangeKey = "7d";

export const RANGE_OPTIONS: ReadonlyArray<{
  value: RangeKey;
  label: string;
  description: string;
  windowMinutes: number;
}> = [
  { value: "1h", label: "1H", description: "Last hour", windowMinutes: 60 },
  {
    value: "24h",
    label: "24H",
    description: "Last 24 hours",
    windowMinutes: 60 * 24,
  },
  { value: "7d", label: "7D", description: "Last 7 days", windowMinutes: 60 * 24 * 7 },
  {
    value: "30d",
    label: "30D",
    description: "Last 30 days",
    windowMinutes: 60 * 24 * 30,
  },
] as const;

export function parseRange(raw: string | undefined | null): RangeKey {
  if (raw === "1h" || raw === "24h" || raw === "7d" || raw === "30d") {
    return raw;
  }
  return DEFAULT_RANGE;
}

export function rangeWindowMs(range: RangeKey): number {
  const option = RANGE_OPTIONS.find((item) => item.value === range);
  return (option?.windowMinutes ?? 60 * 24 * 7) * 60 * 1000;
}

export type SeriesPoint = {
  label: string;
  value: number;
  iso: string;
};

type BucketConfig = {
  count: number;
  stepMs: number;
  labelFor: (date: Date, index: number) => string;
};

function bucketsForRange(range: RangeKey, now: Date): BucketConfig {
  switch (range) {
    case "1h":
      return {
        count: 12,
        stepMs: 5 * 60 * 1000,
        labelFor: (date) =>
          date.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          }),
      };
    case "24h":
      return {
        count: 24,
        stepMs: 60 * 60 * 1000,
        labelFor: (date) =>
          date.toLocaleTimeString(undefined, {
            hour: "2-digit",
            hour12: false,
          }),
      };
    case "30d":
      return {
        count: 30,
        stepMs: 24 * 60 * 60 * 1000,
        labelFor: (date) =>
          date.toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          }),
      };
    case "7d":
    default:
      return {
        count: 7,
        stepMs: 24 * 60 * 60 * 1000,
        labelFor: (date) =>
          date.toLocaleDateString(undefined, { weekday: "short" }),
      };
  }
}

export function buildActivitySeries(
  incidents: IncidentSummary[],
  range: RangeKey,
): SeriesPoint[] {
  const now = new Date();
  const { count, stepMs, labelFor } = bucketsForRange(range, now);

  const buckets: SeriesPoint[] = [];
  for (let offset = count - 1; offset >= 0; offset -= 1) {
    const bucketStart = new Date(now.getTime() - offset * stepMs);
    if (range === "7d" || range === "30d") {
      bucketStart.setHours(0, 0, 0, 0);
    } else if (range === "24h") {
      bucketStart.setMinutes(0, 0, 0);
    } else {
      const minutes = bucketStart.getMinutes();
      bucketStart.setMinutes(minutes - (minutes % 5), 0, 0);
    }
    buckets.push({
      label: labelFor(bucketStart, count - 1 - offset),
      value: 0,
      iso: bucketStart.toISOString(),
    });
  }

  const firstMs = new Date(buckets[0]?.iso ?? now.toISOString()).getTime();
  const lastMs = firstMs + count * stepMs;

  for (const incident of incidents) {
    const last = new Date(incident.last_seen_at).getTime();
    if (Number.isNaN(last)) continue;
    if (last < firstMs || last >= lastMs) continue;
    const index = Math.min(
      Math.floor((last - firstMs) / stepMs),
      buckets.length - 1,
    );
    const bucket = buckets[index];
    if (bucket) {
      bucket.value += 1;
    }
  }

  return buckets;
}

export function filterIncidentsByRange(
  incidents: IncidentSummary[],
  range: RangeKey,
): IncidentSummary[] {
  const cutoff = Date.now() - rangeWindowMs(range);
  return incidents.filter((incident) => {
    const last = new Date(incident.last_seen_at).getTime();
    return !Number.isNaN(last) && last >= cutoff;
  });
}

export function buildHeatmap(
  incidents: IncidentSummary[],
): { days: string[]; hours: number[]; matrix: number[][]; max: number } {
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - 6);

  const days: string[] = [];
  for (let i = 0; i < 7; i += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    days.push(day.toLocaleDateString(undefined, { weekday: "short" }));
  }

  const matrix: number[][] = Array.from({ length: 7 }, () =>
    Array.from({ length: 24 }, () => 0),
  );

  for (const incident of incidents) {
    const last = new Date(incident.last_seen_at);
    if (Number.isNaN(last.getTime())) continue;
    const diffDays = Math.floor(
      (last.getTime() - start.getTime()) / (24 * 60 * 60 * 1000),
    );
    if (diffDays < 0 || diffDays > 6) continue;
    const hour = last.getHours();
    matrix[diffDays][hour] += 1;
  }

  const max = matrix.reduce(
    (acc, row) => Math.max(acc, ...row),
    0,
  );

  return {
    days,
    hours: Array.from({ length: 24 }, (_, i) => i),
    matrix,
    max,
  };
}

export type HeroDelta =
  | { direction: "up" | "down" | "flat"; magnitude: string }
  | null;

export function formatSecondsShort(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 6) / 10;
  return `${hours}h`;
}

export function formatPercent(value: number | null | undefined, fractionDigits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatDelta(
  delta: number | null | undefined,
  unit: "pp" | "s" | "%",
): HeroDelta {
  if (delta == null || !Number.isFinite(delta)) return null;
  if (Math.abs(delta) < 0.01) {
    return { direction: "flat", magnitude: "0" };
  }
  const direction = delta > 0 ? "up" : "down";
  const absValue = Math.abs(delta);
  const magnitude =
    unit === "s"
      ? `${absValue >= 60 ? `${Math.round(absValue / 60)}m` : `${Math.round(absValue)}s`}`
      : `${absValue.toFixed(unit === "pp" ? 1 : 1)}${unit === "pp" ? "pp" : "%"}`;
  return { direction, magnitude };
}

export type MetricsExportPayload = {
  generated_at: string;
  project_id: string;
  range: RangeKey;
  reporting: IncidentReportingOverview;
  suppression: SuppressionSummary | null;
  incidents: IncidentSummary[];
  activity_series: SeriesPoint[];
};

export function buildCsv(incidents: IncidentSummary[]): string {
  const columns: (keyof IncidentSummary)[] = [
    "id",
    "project_id",
    "service",
    "environment",
    "severity",
    "status",
    "event_count",
    "fingerprint",
    "first_seen_at",
    "last_seen_at",
    "created_at",
    "updated_at",
    "title",
  ];
  const escape = (value: unknown): string => {
    if (value == null) return "";
    const str = String(value);
    if (str.includes(",") || str.includes("\"") || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const header = columns.join(",");
  const rows = incidents.map((incident) =>
    columns.map((col) => escape(incident[col])).join(","),
  );
  return [header, ...rows].join("\n");
}

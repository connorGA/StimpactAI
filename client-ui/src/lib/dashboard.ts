import type { IncidentSummary } from "@/lib/types";

type GroupCount = {
  label: string;
  count: number;
};

type NamedValuePoint = {
  label: string;
  value: number;
};

const severityOrder = ["critical", "high", "medium", "low"] as const;

export function formatTimestamp(timestamp: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

export function countOpenIncidents(incidents: IncidentSummary[]): number {
  return incidents.filter((incident) => incident.status === "open").length;
}

export function countCriticalIncidents(incidents: IncidentSummary[]): number {
  return incidents.filter((incident) => incident.severity === "critical").length;
}

export function totalEventVolume(incidents: IncidentSummary[]): number {
  return incidents.reduce((sum, incident) => sum + incident.event_count, 0);
}

export function getTopServices(incidents: IncidentSummary[], limit = 5): GroupCount[] {
  return aggregateCounts(incidents.map((incident) => incident.service), limit);
}

export function getTopProjects(incidents: IncidentSummary[], limit = 5): GroupCount[] {
  return aggregateCounts(incidents.map((incident) => incident.project_id), limit);
}

export function getEnvironmentBreakdown(
  incidents: IncidentSummary[],
  limit = 5,
): GroupCount[] {
  return aggregateCounts(incidents.map((incident) => incident.environment), limit);
}

export function getSeverityBreakdown(incidents: IncidentSummary[]): GroupCount[] {
  const counts = new Map<string, number>();

  for (const severity of severityOrder) {
    counts.set(severity, 0);
  }

  for (const incident of incidents) {
    counts.set(incident.severity, (counts.get(incident.severity) ?? 0) + 1);
  }

  return severityOrder.map((severity) => ({
    label: severity,
    count: counts.get(severity) ?? 0,
  }));
}

export function calculateBarWidth(count: number, max: number): string {
  if (max <= 0) {
    return "0%";
  }

  return `${Math.max(8, Math.round((count / max) * 100))}%`;
}

export function calculateUptimePreview(incidents: IncidentSummary[]): string {
  const openWeight = incidents.reduce((sum, incident) => {
    if (incident.status !== "open") {
      return sum;
    }

    const severityPenalty =
      incident.severity === "critical"
        ? 0.08
        : incident.severity === "high"
          ? 0.04
          : incident.severity === "medium"
            ? 0.02
            : 0.01;

    return sum + severityPenalty;
  }, 0);

  const uptime = Math.max(99.5, 99.99 - openWeight);
  return `${uptime.toFixed(2)}%`;
}

export function getLiveStatusSummary(incidents: IncidentSummary[]): {
  title: string;
  detail: string;
  tone: "healthy" | "incident";
} {
  const openIncidents = countOpenIncidents(incidents);

  if (openIncidents === 0) {
    return {
      title: "All monitored services look healthy",
      detail: "No open incidents are currently visible in the live queue.",
      tone: "healthy",
    };
  }

  return {
    title: `${openIncidents} active incident${openIncidents === 1 ? "" : "s"} need attention`,
    detail: "The live queue indicates active production impact and should remain the main response surface.",
    tone: "incident",
  };
}

export function buildIncidentTrendSeries(incidents: IncidentSummary[]): NamedValuePoint[] {
  const openIncidents = countOpenIncidents(incidents);
  const total = Math.max(incidents.length, 1);

  return ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"].map(
    (label, index) => ({
      label,
      value: Math.max(1, Math.round((total * (index + 2)) / 10) + (index % 2 === 0 ? openIncidents : 0)),
    }),
  );
}

export function buildUptimeSeries(incidents: IncidentSummary[]): NamedValuePoint[] {
  const openIncidents = countOpenIncidents(incidents);
  const criticalIncidents = countCriticalIncidents(incidents);
  const base = 99.94 - openIncidents * 0.01 - criticalIncidents * 0.015;

  return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label, index) => ({
    label,
    value: Number((Math.max(99.55, base + ((index % 3) - 1) * 0.05)).toFixed(2)),
  }));
}

export function buildLatencySeries(incidents: IncidentSummary[]): NamedValuePoint[] {
  const eventVolume = totalEventVolume(incidents);
  const base = 180 + Math.min(eventVolume * 2, 180);

  return ["API", "Workers", "Storage", "Copilot"].map((label, index) => ({
    label,
    value: Math.round(base - index * 18 + ((index % 2) * 16)),
  }));
}

export function getServiceHealthRows(incidents: IncidentSummary[]): Array<{
  label: string;
  status: "healthy" | "watch" | "critical";
}> {
  const services = getTopServices(incidents, 4);

  return services.map((service, index) => ({
    label: service.label,
    status:
      index === 0 && service.count > 1
        ? "critical"
        : service.count > 1
          ? "watch"
          : "healthy",
  }));
}

export function calculateLinePath(points: NamedValuePoint[], height: number, width: number): string {
  if (points.length === 0) {
    return "";
  }

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);

  return points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * width;
      const y = height - ((point.value - min) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function aggregateCounts(values: string[], limit: number): GroupCount[] {
  const counts = new Map<string, number>();

  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }));
}

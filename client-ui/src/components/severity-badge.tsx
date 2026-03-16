import type { IncidentSeverity } from "@/lib/types";

const severityClasses: Record<IncidentSeverity, string> = {
  low: "vault-badge bg-[rgba(79,124,255,0.08)] text-[#315de2] border-[rgba(79,124,255,0.18)]",
  medium:
    "vault-badge bg-[rgba(255,184,77,0.15)] text-[#a05c00] border-[rgba(255,184,77,0.28)]",
  high: "vault-badge bg-[rgba(255,106,61,0.12)] text-[#d44921] border-[rgba(255,106,61,0.24)]",
  critical:
    "vault-badge bg-[linear-gradient(180deg,rgba(255,106,61,0.16),rgba(255,184,77,0.14))] text-[#b63412] border-[rgba(255,106,61,0.28)]",
};

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset ${severityClasses[severity]}`}
    >
      {severity}
    </span>
  );
}

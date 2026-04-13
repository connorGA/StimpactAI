import type { IncidentSeverity } from "@/lib/types";

const severityConfig: Record<IncidentSeverity, { className: string }> = {
  low: { className: "bg-[#eff6ff] text-[#2563eb]" },
  medium: { className: "bg-[#fffbeb] text-[#d97706]" },
  high: { className: "bg-[#fff7ed] text-[#ea580c]" },
  critical: { className: "bg-[#fef2f2] text-[#dc2626]" },
};

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  const { className } = severityConfig[severity];
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ${className}`}>
      {severity}
    </span>
  );
}

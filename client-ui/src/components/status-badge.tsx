import type { IncidentStatus } from "@/lib/types";

const statusClasses: Record<IncidentStatus, string> = {
  open: "vault-badge bg-[rgba(255,106,61,0.1)] text-[#c9431d] border-[rgba(255,106,61,0.2)]",
  resolved:
    "vault-badge bg-[rgba(22,164,109,0.08)] text-[#13724d] border-[rgba(22,164,109,0.18)]",
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset ${statusClasses[status]}`}
    >
      {status}
    </span>
  );
}

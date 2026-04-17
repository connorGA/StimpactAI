import type { IncidentStatus } from "@/lib/types";

const statusConfig: Record<IncidentStatus, { className: string; dot: string }> = {
  open: { className: "text-[#dc2626]", dot: "bg-[#dc2626]" },
  acknowledged: { className: "text-[#f59e0b]", dot: "bg-[#f59e0b]" },
  resolved: { className: "text-[#16a34a]", dot: "bg-[#16a34a]" },
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const { className, dot } = statusConfig[status];
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium capitalize ${className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {status}
    </span>
  );
}

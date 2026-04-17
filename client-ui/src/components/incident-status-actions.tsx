"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { IncidentStatus, IncidentSummary } from "@/lib/types";

type IncidentStatusActionsProps = {
  incidentId: string;
  status: IncidentStatus;
  className?: string;
  compact?: boolean;
};

export function IncidentStatusActions({
  incidentId,
  status,
  className = "",
  compact = false,
}: IncidentStatusActionsProps) {
  const router = useRouter();
  const [activeAction, setActiveAction] = useState<"acknowledge" | "reopen" | null>(
    null,
  );
  const [actionError, setActionError] = useState<string | null>(null);

  async function runAction(action: "acknowledge" | "reopen") {
    setActionError(null);
    setActiveAction(action);
    try {
      const response = await fetch(`/api/incidents/${incidentId}/${action}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) {
        let message = `Failed to ${action} incident.`;
        try {
          const payload = (await response.json()) as { error?: { message?: string } };
          if (payload.error?.message) {
            message = payload.error.message;
          }
        } catch {
          // Keep the fallback error message.
        }
        throw new Error(message);
      }
      await response.json().catch(() => null as IncidentSummary | null);
      router.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `Failed to ${action} incident.`);
    } finally {
      setActiveAction(null);
    }
  }

  const buttonClassName = compact
    ? "rounded-md border border-white/10 bg-white/[0.05] px-2.5 py-1 text-[11px] font-medium text-white/70 transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:text-white/35"
    : "rounded-lg border border-white/10 bg-white/[0.05] px-3.5 py-2 text-sm font-medium text-white/75 transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:text-white/35";

  return (
    <div className={`flex flex-col items-start gap-2 ${className}`.trim()}>
      <div className="flex flex-wrap gap-2">
        {status === "open" ? (
          <button
            type="button"
            onClick={() => void runAction("acknowledge")}
            disabled={activeAction !== null}
            className={buttonClassName}
            title="Keep the incident unresolved, but clear it from the active incident queue."
          >
            {activeAction === "acknowledge" ? "Acknowledging..." : "Acknowledge"}
          </button>
        ) : null}
        {status !== "open" ? (
          <button
            type="button"
            onClick={() => void runAction("reopen")}
            disabled={activeAction !== null}
            className={buttonClassName}
          >
            {activeAction === "reopen" ? "Reopening..." : "Reopen"}
          </button>
        ) : null}
      </div>
      {actionError ? <p className="text-xs text-[#fca5a5]">{actionError}</p> : null}
    </div>
  );
}

"use client";

import { Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { TelemetryClassification } from "@/lib/types";

type NoiseReclassifyFormProps = {
  projectId: string;
  fingerprint: string;
  currentClassification: string;
};

const OPTIONS: { value: TelemetryClassification; label: string }[] = [
  { value: "code_bug", label: "Treat as bug" },
  { value: "user_error", label: "Mark as user error" },
  { value: "code_ambiguous", label: "Needs human review" },
];

export function NoiseReclassifyForm({
  projectId,
  fingerprint,
  currentClassification,
}: NoiseReclassifyFormProps) {
  const router = useRouter();
  const listId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [escalateHint, setEscalateHint] = useState<string | null>(null);
  const [escalatedIncidentId, setEscalatedIncidentId] = useState<string | null>(null);
  const [selection, setSelection] = useState<TelemetryClassification>(() => {
    if (
      currentClassification === "code_bug" ||
      currentClassification === "user_error" ||
      currentClassification === "code_ambiguous"
    ) {
      return currentClassification;
    }
    return "user_error";
  });

  const selectedLabel =
    OPTIONS.find((o) => o.value === selection)?.label ?? selection;

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(event: PointerEvent) {
      const el = containerRef.current;
      if (el && !el.contains(event.target as Node)) {
        closeMenu();
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") closeMenu();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen, closeMenu]);

  async function handleEscalate() {
    setIsSubmitting(true);
    setError(null);
    setEscalateHint(null);
    setEscalatedIncidentId(null);
    try {
      const response = await fetch(
        `/api/incidents/noise/${encodeURIComponent(fingerprint)}/escalate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            reason: reason.trim() || undefined,
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        throw new Error(payload?.error?.message ?? "Escalation failed.");
      }
      const data = (await response.json()) as {
        incident_id: string;
        autonomous_trigger_skipped?: boolean;
      };
      setEscalatedIncidentId(data.incident_id);
      setEscalateHint(
        data.autonomous_trigger_skipped
          ? "Incident opened — a repair run is already active for this incident."
          : "Incident opened — repair queued.",
      );
      router.refresh();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Escalation failed.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setEscalateHint(null);
    try {
      const response = await fetch(
        `/api/incidents/noise/${encodeURIComponent(fingerprint)}/reclassify`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            classification: selection,
            reason: reason.trim() || undefined,
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        throw new Error(payload?.error?.message ?? "Reclassification failed.");
      }
      router.refresh();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Reclassification failed.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <div ref={containerRef} className="relative min-w-[11.5rem]">
          <button
            type="button"
            disabled={isSubmitting}
            aria-expanded={menuOpen}
            aria-haspopup="listbox"
            aria-controls={listId}
            className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-white/15 bg-white/[0.07] px-2.5 py-1.5 text-left text-[12px] font-medium text-white/90 shadow-inner shadow-black/25 transition hover:border-white/22 focus:border-sky-400/45 focus:outline-none focus:ring-2 focus:ring-sky-400/15 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="min-w-0 truncate">{selectedLabel}</span>
            <ChevronDown
              aria-hidden
              className={`h-3.5 w-3.5 shrink-0 text-white/45 transition-transform ${menuOpen ? "rotate-180" : ""}`}
            />
          </button>

          {menuOpen ? (
            <ul
              id={listId}
              role="listbox"
              aria-label="Classification"
              className="absolute left-0 top-[calc(100%+4px)] z-50 min-w-full overflow-hidden rounded-lg border border-white/15 bg-[#141418] py-1 shadow-xl shadow-black/50 ring-1 ring-white/5"
            >
              {OPTIONS.map((option) => {
                const isSelected = option.value === selection;
                return (
                  <li key={option.value} role="presentation">
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-[12px] text-white/90 transition hover:bg-white/[0.08] focus:bg-white/[0.08] focus:outline-none"
                      onClick={() => {
                        setSelection(option.value);
                        closeMenu();
                      }}
                    >
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                        {isSelected ? (
                          <Check className="h-3.5 w-3.5 text-sky-300" strokeWidth={2.5} />
                        ) : null}
                      </span>
                      <span className="min-w-0 flex-1">{option.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
        <button
          type="submit"
          className="rounded-md border border-white/10 bg-white/[0.06] px-2 py-1 text-[11px] font-semibold text-white/80 transition hover:bg-white/[0.12] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          title="Mark as bug, open an incident from the latest event, and queue autonomous repair"
          className="rounded-md border border-sky-400/25 bg-sky-500/[0.12] px-2 py-1 text-[11px] font-semibold text-sky-100/95 transition hover:bg-sky-500/[0.2] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isSubmitting}
          onClick={() => void handleEscalate()}
        >
          {isSubmitting ? "Working…" : "Open incident & repair"}
        </button>
      </div>
      <input
        type="text"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Reason (optional)"
        className="w-full rounded-md border border-white/10 bg-black/40 px-2 py-1 text-[11px] text-white placeholder:text-white/40 focus:outline-none focus:ring-1 focus:ring-white/30"
        disabled={isSubmitting}
      />
      {escalateHint && escalatedIncidentId ? (
        <p className="text-[11px] text-emerald-200/90">
          {escalateHint}{" "}
          <Link
            href={`/incidents/${encodeURIComponent(escalatedIncidentId)}?project_id=${encodeURIComponent(projectId)}`}
            className="underline underline-offset-2 hover:text-emerald-100"
          >
            View incident
          </Link>
        </p>
      ) : null}
      {error ? <p className="text-[11px] text-[#ff6a3d]">{error}</p> : null}
    </form>
  );
}

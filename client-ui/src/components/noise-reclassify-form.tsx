"use client";

import { useState } from "react";
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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
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

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
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
      <div className="flex items-center gap-1.5">
        <select
          value={selection}
          onChange={(event) =>
            setSelection(event.target.value as TelemetryClassification)
          }
          className="rounded-md border border-white/10 bg-black/40 px-2 py-1 text-[12px] text-white focus:outline-none focus:ring-1 focus:ring-white/30"
          disabled={isSubmitting}
        >
          {OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-md border border-white/10 bg-white/[0.06] px-2 py-1 text-[11px] font-semibold text-white/80 transition hover:bg-white/[0.12] disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Saving…" : "Save"}
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
      {error ? <p className="text-[11px] text-[#ff6a3d]">{error}</p> : null}
    </form>
  );
}

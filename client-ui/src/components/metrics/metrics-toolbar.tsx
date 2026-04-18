"use client";

import { Download, Loader2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import type { MetricsExportPayload, RangeKey } from "@/lib/metrics-series";
import { RANGE_OPTIONS, buildCsv } from "@/lib/metrics-series";

type MetricsToolbarProps = {
  currentRange: RangeKey;
  exportPayload: MetricsExportPayload;
};

export function MetricsToolbar({
  currentRange,
  exportPayload,
}: MetricsToolbarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const setRange = useCallback(
    (value: RangeKey) => {
      if (value === currentRange) return;
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      params.set("range", value);
      startTransition(() => {
        router.replace(`${pathname}?${params.toString()}`, { scroll: false });
      });
    },
    [currentRange, pathname, router, searchParams],
  );

  const triggerDownload = useCallback(
    (blob: Blob, filename: string) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    },
    [],
  );

  const exportJson = useCallback(() => {
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json",
    });
    const date = new Date().toISOString().slice(0, 10);
    triggerDownload(blob, `stimpact-metrics-${currentRange}-${date}.json`);
    setMenuOpen(false);
  }, [currentRange, exportPayload, triggerDownload]);

  const exportCsv = useCallback(() => {
    const blob = new Blob([buildCsv(exportPayload.incidents)], {
      type: "text/csv;charset=utf-8;",
    });
    const date = new Date().toISOString().slice(0, 10);
    triggerDownload(blob, `stimpact-incidents-${currentRange}-${date}.csv`);
    setMenuOpen(false);
  }, [currentRange, exportPayload.incidents, triggerDownload]);

  const copyJson = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(exportPayload, null, 2));
    } catch {
      // ignore
    }
    setMenuOpen(false);
  }, [exportPayload]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex items-center gap-0.5 rounded-full border border-white/10 bg-white/[0.04] p-0.5 backdrop-blur">
        {RANGE_OPTIONS.map((option) => {
          const active = option.value === currentRange;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setRange(option.value)}
              title={option.description}
              className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                active
                  ? "bg-[linear-gradient(135deg,#ff8b68,#ff5a2a)] text-white shadow-[0_6px_16px_rgba(255,106,61,0.35)]"
                  : "text-white/55 hover:bg-white/[0.05] hover:text-white/85"
              }`}
              disabled={isPending}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <div className="relative" ref={menuRef}>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-[12px] font-semibold text-white/80 transition hover:border-white/25 hover:bg-white/[0.07] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/25"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
        >
          {isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-white/60" />
          ) : (
            <Download className="h-3.5 w-3.5 text-white/70" />
          )}
          Export
        </button>
        {menuOpen ? (
          <div
            role="menu"
            className="absolute right-0 top-[calc(100%+6px)] z-50 w-56 overflow-hidden rounded-xl border border-white/10 bg-[#0d1320]/95 shadow-xl shadow-black/60 ring-1 ring-white/5 backdrop-blur"
          >
            <button
              type="button"
              role="menuitem"
              onClick={exportJson}
              className="flex w-full flex-col items-start gap-0.5 px-3.5 py-2.5 text-left text-[13px] text-white/90 transition hover:bg-white/[0.06]"
            >
              <span className="font-semibold">Download JSON</span>
              <span className="text-[11px] text-white/45">
                Full reporting payload + incidents
              </span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={exportCsv}
              className="flex w-full flex-col items-start gap-0.5 border-t border-white/5 px-3.5 py-2.5 text-left text-[13px] text-white/90 transition hover:bg-white/[0.06]"
            >
              <span className="font-semibold">Incidents as CSV</span>
              <span className="text-[11px] text-white/45">
                Spreadsheet-friendly flat table
              </span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={copyJson}
              className="flex w-full flex-col items-start gap-0.5 border-t border-white/5 px-3.5 py-2.5 text-left text-[13px] text-white/90 transition hover:bg-white/[0.06]"
            >
              <span className="font-semibold">Copy JSON to clipboard</span>
              <span className="text-[11px] text-white/45">Quick paste into tools</span>
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

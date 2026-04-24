"use client";

import { Check, ChevronDown } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

export type DarkListboxOption = { value: string; label: string };

type DarkListboxSelectProps = {
  options: DarkListboxOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  /** Extra classes on the outer `relative` wrapper (e.g. `mt-1.5 max-w-md`). */
  className?: string;
  "aria-label"?: string;
  /** `compact` matches incident noise controls; `comfortable` for form rows. */
  size?: "compact" | "comfortable";
};

const buttonSize: Record<NonNullable<DarkListboxSelectProps["size"]>, string> = {
  compact:
    "px-2.5 py-1.5 text-[12px] font-medium",
  comfortable:
    "px-3 py-2.5 text-sm font-medium",
};

const listSize: Record<NonNullable<DarkListboxSelectProps["size"]>, string> = {
  compact: "text-[12px]",
  comfortable: "text-sm",
};

const rowSize: Record<NonNullable<DarkListboxSelectProps["size"]>, string> = {
  compact: "px-2.5 py-2",
  comfortable: "px-3 py-2.5",
};

export function DarkListboxSelect({
  options,
  value,
  onChange,
  disabled = false,
  className = "",
  "aria-label": ariaLabel,
  size = "comfortable",
}: DarkListboxSelectProps) {
  const listId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const selected = options.find((o) => o.value === value);
  const displayLabel = selected?.label ?? options[0]?.label ?? "Choose…";

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const el = containerRef.current;
      if (el && !el.contains(event.target as Node)) {
        close();
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, close]);

  return (
    <div ref={containerRef} className={`relative ${className}`.trim()}>
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-label={ariaLabel}
        className={`flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-white/15 bg-white/[0.07] text-left text-white/90 shadow-inner shadow-black/25 transition hover:border-white/22 focus:border-sky-400/45 focus:outline-none focus:ring-2 focus:ring-sky-400/15 disabled:cursor-not-allowed disabled:opacity-50 ${buttonSize[size]}`}
        onClick={() => !disabled && setOpen((o) => !o)}
      >
        <span className="min-w-0 truncate">{displayLabel}</span>
        <ChevronDown
          aria-hidden
          className={`h-3.5 w-3.5 shrink-0 text-white/45 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <ul
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          className={`absolute left-0 top-[calc(100%+4px)] z-50 max-h-[min(280px,70vh)] min-w-full overflow-y-auto rounded-lg border border-white/15 bg-[#141418] py-1 shadow-xl shadow-black/50 ring-1 ring-white/5 ${listSize[size]}`}
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <li key={option.value} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`flex w-full items-center gap-2 text-left text-white/90 transition hover:bg-white/[0.08] focus:bg-white/[0.08] focus:outline-none ${rowSize[size]}`}
                  onClick={() => {
                    onChange(option.value);
                    close();
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
  );
}

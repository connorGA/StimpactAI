type PageLoadSpinnerProps = {
  /** Shown below the spinner for screen readers and as subtle UI copy. */
  label?: string;
};

/** Centered circular loader for Next.js `loading.tsx` route fallbacks. */
export function PageLoadSpinner({ label = "Loading" }: PageLoadSpinnerProps) {
  return (
    <div className="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-4 px-4 py-8">
      <span
        className="inline-flex h-10 w-10 animate-spin rounded-full border-2 border-white/15 border-t-[#ff6a3d]"
        role="status"
        aria-label={label}
      />
      <p className="text-sm text-white/45">{label}…</p>
    </div>
  );
}

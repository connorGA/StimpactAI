"use client";

export default function AppLoading() {
  return (
    <div className="flex min-h-[calc(100vh-7rem)] items-center justify-center px-6 lg:min-h-[calc(100vh-9.5rem)]">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="inline-flex h-9 w-9 animate-spin rounded-full border-2 border-[rgba(23,56,93,0.18)] border-t-[rgba(255,106,61,0.88)]" />
        <p className="text-sm font-medium text-[#746d66]">Loading..</p>
      </div>
    </div>
  );
}

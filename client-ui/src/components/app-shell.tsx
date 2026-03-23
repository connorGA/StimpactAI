"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";

import { AppShellNav } from "@/components/app-shell-nav";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  if (pathname === "/") {
    return <>{children}</>;
  }

  const sidebarWidthClass = collapsed ? "lg:w-0" : "lg:w-[248px]";
  const contentOffsetClass = collapsed ? "lg:pl-0" : "lg:pl-[248px]";

  return (
    <div className="h-screen overflow-hidden bg-transparent">
      <aside
        className={`vault-sidebar fixed inset-y-0 left-0 z-40 hidden overflow-hidden border-r border-[rgba(17,24,39,0.08)] transition-[width] duration-200 lg:flex lg:flex-col ${
          sidebarWidthClass
        }`}
      >
        <div className="border-b border-[rgba(17,24,39,0.08)] px-5 py-5">
          <p className="text-lg font-semibold tracking-tight text-white">Stimpact</p>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-5">
          <AppShellNav compact={false} />
        </div>

        <div className="border-t border-[rgba(255,255,255,0.06)] px-4 py-4">
          <div className="rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-white/5 px-4 py-4 text-white/86">
            <p
              className={`text-[11px] font-semibold uppercase tracking-[0.16em] ${
                collapsed ? "text-center" : ""
              }`}
            >
              {collapsed ? "Live" : "Live workspace"}
            </p>
            <p
              className={`mt-2 text-sm leading-6 text-white/58 ${
                collapsed ? "hidden" : "block"
              }`}
            >
              Streaming incident updates, policy enforcement, and onboarding are available from the live workspace.
            </p>
          </div>
        </div>

        <button
          type="button"
          aria-label="Collapse sidebar"
          onClick={() => setCollapsed(true)}
          className="absolute inset-y-0 right-0 w-3 cursor-ew-resize bg-transparent transition hover:bg-white/6"
        />
      </aside>

      <div className={`flex h-screen flex-col ${contentOffsetClass}`}>
        {collapsed ? (
          <button
            type="button"
            aria-label="Open sidebar"
            onClick={() => setCollapsed(false)}
            className="fixed left-4 top-3 z-50 hidden h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,24,39,0.08)] bg-[#121826] text-white shadow-[0_10px_28px_rgba(15,23,42,0.22)] transition hover:border-[rgba(255,90,42,0.24)] hover:bg-[#1a2130] lg:flex"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 6.75 15 12l-6 5.25" />
            </svg>
          </button>
        ) : null}

        <div className="px-4 py-4 lg:hidden">
          <MobileTopBar />
          <div className="mt-4">
            <AppShellNav mobile />
          </div>
        </div>

        <div className="hidden lg:block">
          <DesktopTopBar collapsed={collapsed} />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-4 lg:px-8 lg:pb-10 lg:pt-20">
          <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

function DesktopTopBar({ collapsed }: { collapsed: boolean }) {
  return (
    <header
      className={`vault-topnav fixed right-0 top-0 z-30 hidden h-16 items-center transition-[left] duration-200 lg:flex ${
        collapsed ? "left-0" : "left-[248px]"
      }`}
    >
      <div className="flex h-full w-full items-center justify-between px-8">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-white/14 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-white">
            Production
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Operations workspace</p>
            <p className="text-xs text-white/70">
              Live monitoring, metrics, and controlled autonomy
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Settings"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/18 bg-white/10 text-white transition hover:bg-white/16"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3.2" />
              <path d="M12 2.75v2.1" />
              <path d="M12 19.15v2.1" />
              <path d="m4.93 4.93 1.49 1.49" />
              <path d="m17.58 17.58 1.49 1.49" />
              <path d="M2.75 12h2.1" />
              <path d="M19.15 12h2.1" />
              <path d="m4.93 19.07 1.49-1.49" />
              <path d="m17.58 6.42 1.49-1.49" />
            </svg>
          </button>
          <button
            type="button"
            aria-label="Notifications"
            className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-white/18 bg-white/10 text-white transition hover:bg-white/16"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M6.75 9.5a5.25 5.25 0 1 1 10.5 0c0 6 2.25 7.5 2.25 7.5H4.5s2.25-1.5 2.25-7.5" />
              <path d="M10.15 20a2.2 2.2 0 0 0 3.7 0" />
            </svg>
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-white" />
          </button>
          <div className="flex items-center gap-3 border-l border-white/18 pl-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[linear-gradient(180deg,#ff754b,#ff5a2a)] text-sm font-semibold text-white">
              HK
            </div>
            <div className="pr-1 text-white">
              <p className="text-sm font-semibold">Henry Klein</p>
              <p className="text-xs text-white/70">Admin workspace</p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function MobileTopBar() {
  return (
    <div className="vault-topnav px-4 py-3 lg:hidden">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">Stimpact</p>
          <p className="text-xs text-white/70">Operations workspace</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Settings"
            className="flex h-10 w-10 items-center justify-center rounded-full border border-white/18 bg-white/10 text-white"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3.2" />
              <path d="M12 2.75v2.1" />
              <path d="M12 19.15v2.1" />
              <path d="m4.93 4.93 1.49 1.49" />
              <path d="m17.58 17.58 1.49 1.49" />
              <path d="M2.75 12h2.1" />
              <path d="M19.15 12h2.1" />
              <path d="m4.93 19.07 1.49-1.49" />
              <path d="m17.58 6.42 1.49-1.49" />
            </svg>
          </button>
          <button
            type="button"
            aria-label="Notifications"
            className="relative flex h-10 w-10 items-center justify-center rounded-full border border-white/18 bg-white/10 text-white"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M6.75 9.5a5.25 5.25 0 1 1 10.5 0c0 6 2.25 7.5 2.25 7.5H4.5s2.25-1.5 2.25-7.5" />
              <path d="M10.15 20a2.2 2.2 0 0 0 3.7 0" />
            </svg>
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-white" />
          </button>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[linear-gradient(180deg,#ff754b,#ff5a2a)] text-xs font-semibold text-white">
            HK
          </div>
        </div>
      </div>
    </div>
  );
}

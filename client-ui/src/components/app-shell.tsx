"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppShellNav } from "@/components/app-shell-nav";
import { BrandMark } from "@/components/brand-mark";
import type { AuthSession } from "@/lib/types";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [pendingNavHref, setPendingNavHref] = useState<string | null>(null);

  const isPublicRoute =
    pathname === "/" || pathname === "/login" || pathname === "/signup";

  useEffect(() => {
    if (isPublicRoute) {
      setSession(null);
      setSessionLoading(false);
      return;
    }

    let cancelled = false;

    async function loadSession() {
      setSessionLoading(true);
      try {
        const response = await fetch("/api/auth/session", { method: "GET" });
        if (!response.ok) {
          throw new Error("Unable to load session.");
        }
        const payload = (await response.json()) as Omit<AuthSession, "access_token">;
        if (!cancelled) {
          setSession({ ...payload, access_token: "" });
          setSelectedProjectId(readCurrentProjectCookie());
        }
      } catch {
        if (!cancelled) {
          setSession(null);
        }
      } finally {
        if (!cancelled) {
          setSessionLoading(false);
        }
      }
    }

    void loadSession();

    return () => {
      cancelled = true;
    };
  }, [isPublicRoute]);

  useEffect(() => {
    if (!pendingNavHref) {
      return;
    }
    if (pathname === pendingNavHref || pathname.startsWith(`${pendingNavHref}/`)) {
      setPendingNavHref(null);
    }
  }, [pathname, pendingNavHref]);

  function handleShellNavigate(href: string) {
    if (pathname === href || pathname.startsWith(`${href}/`)) {
      setPendingNavHref(null);
      return;
    }
    setPendingNavHref(href);
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", {
      method: "POST",
    });
    setSession(null);
    router.push("/login");
    router.refresh();
  }

  async function handleProjectSwitch(projectId: string | null) {
    await fetch("/api/projects/current", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ project_id: projectId }),
    });
    setSelectedProjectId(projectId);
    router.refresh();
  }

  if (isPublicRoute) {
    return <>{children}</>;
  }

  const sidebarWidthClass = collapsed ? "lg:w-0" : "lg:w-[248px]";
  const contentOffsetClass = collapsed ? "lg:ml-0" : "lg:ml-[248px]";
  const currentProject =
    (selectedProjectId
      ? session?.projects.find((project) => project.id === selectedProjectId) ?? null
      : null) ??
    session?.projects[0] ??
    null;

  return (
    <div className="h-screen overflow-hidden bg-transparent">
      <div className="hidden lg:block">
        <DesktopTopBar
          session={session}
          currentProject={currentProject}
          sessionLoading={sessionLoading}
          onProjectSwitch={handleProjectSwitch}
          onLogout={handleLogout}
        />
      </div>

      <aside
        className={`vault-sidebar fixed bottom-0 left-0 top-16 z-30 hidden overflow-hidden border-r border-[rgba(17,24,39,0.08)] transition-[width] duration-200 lg:flex lg:flex-col ${
          sidebarWidthClass
        }`}
      >
        <div className="flex-1 overflow-y-auto px-4 py-5">
          <AppShellNav compact={false} pendingHref={pendingNavHref} onNavigate={handleShellNavigate} />
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
            className="fixed left-4 top-20 z-40 hidden h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,24,39,0.08)] bg-[#121826] text-white shadow-[0_10px_28px_rgba(15,23,42,0.22)] transition hover:border-[rgba(255,90,42,0.24)] hover:bg-[#1a2130] lg:flex"
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
          <MobileTopBar
            session={session}
            currentProject={currentProject}
            sessionLoading={sessionLoading}
            onProjectSwitch={handleProjectSwitch}
            onLogout={handleLogout}
          />
          <div className="mt-4">
            <AppShellNav mobile pendingHref={pendingNavHref} onNavigate={handleShellNavigate} />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-4 lg:px-8 lg:pb-10 lg:pt-[5.5rem]">
          <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-6">
            {pendingNavHref ? <WorkspaceRouteLoading href={pendingNavHref} /> : children}
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkspaceRouteLoading({ href }: { href: string }) {
  void href;

  return (
    <div className="flex min-h-[520px] items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="inline-flex h-9 w-9 animate-spin rounded-full border-2 border-[rgba(23,56,93,0.18)] border-t-[rgba(255,106,61,0.88)]" />
        <p className="text-sm font-medium text-[#746d66]">Loading..</p>
      </div>
    </div>
  );
}

function DesktopTopBar({
  session,
  currentProject,
  sessionLoading,
  onProjectSwitch,
  onLogout,
}: {
  session: AuthSession | null;
  currentProject: AuthSession["projects"][number] | null;
  sessionLoading: boolean;
  onProjectSwitch: (projectId: string | null) => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  const workspaceName = session?.organization.name ?? "Workspace";
  const workspaceRole = session ? `${formatRole(session.role)} workspace` : "Signed-in workspace";

  return (
    <header
      className="vault-topnav fixed left-0 right-0 top-0 z-40 hidden h-16 items-center lg:flex"
    >
      <div className="flex h-full w-full items-center justify-between px-8">
        <div className="flex items-center gap-5">
          <Link href="/live" className="inline-flex items-center gap-3 text-white">
            <BrandMark className="h-11 w-11" />
            <span className="text-base font-semibold tracking-[0.04em]">Stimpact.ai</span>
          </Link>
          <div>
            <p className="text-sm font-semibold text-white">
              {sessionLoading ? "Loading workspace..." : workspaceName}
            </p>
            <p className="text-xs text-white/70">
              Live monitoring, metrics, and controlled autonomy
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ProjectMenu
            projects={session?.projects ?? []}
            currentProjectId={currentProject?.id ?? null}
            onSelect={onProjectSwitch}
          />
          <Link
            href="/control-center"
            aria-label="Settings"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1]"
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
          </Link>
          <Link
            href="/incidents"
            aria-label="Notifications"
            className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1]"
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
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[linear-gradient(180deg,#ffb253,#ff6a3d)]" />
          </Link>
          <AccountMenu
            session={session}
            sessionLoading={sessionLoading}
            subtitle={workspaceRole}
            onLogout={onLogout}
            desktop
          />
        </div>
      </div>
    </header>
  );
}

function MobileTopBar({
  session,
  currentProject,
  sessionLoading,
  onProjectSwitch,
  onLogout,
}: {
  session: AuthSession | null;
  currentProject: AuthSession["projects"][number] | null;
  sessionLoading: boolean;
  onProjectSwitch: (projectId: string | null) => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  return (
    <div className="vault-topnav px-4 py-3 lg:hidden">
      <div className="flex items-center justify-between gap-3">
        <Link href="/live" className="inline-flex items-center gap-3 text-white">
          <BrandMark className="h-10 w-10" />
          <div>
            <p className="text-sm font-semibold text-white">Stimpact.ai</p>
            <p className="text-xs text-white/70">
              {sessionLoading
                ? "Loading workspace..."
                : session?.organization.name ?? "Operations workspace"}
            </p>
          </div>
        </Link>
        <div className="flex items-center gap-2">
          <ProjectMenu
            projects={session?.projects ?? []}
            currentProjectId={currentProject?.id ?? null}
            onSelect={onProjectSwitch}
            compact
          />
          <Link
            href="/control-center"
            aria-label="Settings"
            className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1]"
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
          </Link>
          <Link
            href="/incidents"
            aria-label="Notifications"
            className="relative flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1]"
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
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[linear-gradient(180deg,#ffb253,#ff6a3d)]" />
          </Link>
          <AccountMenu
            session={session}
            sessionLoading={sessionLoading}
            subtitle={session ? `${formatRole(session.role)} workspace` : "Signed-in workspace"}
            onLogout={onLogout}
          />
        </div>
      </div>
    </div>
  );
}

function ProjectMenu({
  projects,
  currentProjectId,
  onSelect,
  compact = false,
}: {
  projects: AuthSession["projects"];
  currentProjectId: string | null;
  onSelect: (projectId: string | null) => Promise<void>;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const activeProject =
    projects.find((project) => project.id === currentProjectId) ?? projects[0] ?? null;

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  if (!activeProject) {
    return null;
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1] ${
          compact ? "h-10 px-3" : "h-10 px-3.5"
        }`}
      >
        <span className="max-w-[120px] truncate text-sm font-semibold">{activeProject.name}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <div className="absolute right-0 top-[calc(100%+0.6rem)] z-50 w-72 rounded-[22px] border border-white/10 bg-[#101725] p-3 shadow-[0_24px_60px_rgba(9,13,22,0.38)]">
          <p className="px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/45">
            Switch project
          </p>
          <div className="mt-3 space-y-2">
            {projects.map((project) => {
              const active = project.id === activeProject.id;
              return (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    void onSelect(project.id);
                  }}
                  className={`w-full rounded-[16px] border px-3 py-3 text-left transition ${
                    active
                      ? "border-[rgba(255,106,61,0.28)] bg-[rgba(255,106,61,0.14)] text-white"
                      : "border-white/8 bg-white/[0.03] text-white/84 hover:border-[rgba(255,106,61,0.16)] hover:bg-white/[0.06]"
                  }`}
                >
                  <p className="text-sm font-semibold">{project.name}</p>
                  <p className="mt-1 text-xs text-white/55">{project.slug}</p>
                </button>
              );
            })}
          </div>
          <Link
            href="/onboarding?create=1"
            onClick={() => setOpen(false)}
            className="mt-3 inline-flex w-full items-center justify-center rounded-[16px] border border-[rgba(255,106,61,0.22)] bg-[rgba(255,106,61,0.12)] px-4 py-3 text-sm font-semibold text-[#ffd7c3] transition hover:border-[rgba(255,106,61,0.4)] hover:bg-[rgba(255,106,61,0.18)] hover:text-white"
          >
            Create new project
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function AccountMenu({
  session,
  sessionLoading,
  subtitle,
  onLogout,
  desktop = false,
}: {
  session: AuthSession | null;
  sessionLoading: boolean;
  subtitle: string;
  onLogout: () => Promise<void>;
  desktop?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  const initials = useMemo(() => buildInitials(session?.user.full_name, session?.user.email), [session]);

  async function handleLogoutClick() {
    setIsLoggingOut(true);
    try {
      await onLogout();
    } finally {
      setIsLoggingOut(false);
      setOpen(false);
    }
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/[0.06] text-white transition hover:border-[rgba(255,106,61,0.2)] hover:bg-white/[0.1] ${
          desktop ? "h-10 pl-2 pr-2.5" : "h-10 w-10 justify-center rounded-full"
        }`}
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[linear-gradient(180deg,#ff754b,#ff5a2a)] text-sm font-semibold text-white">
          {initials}
        </div>
        {desktop ? (
          <div className="pr-0.5 text-left text-white leading-none">
            <p className="text-sm font-semibold leading-none">
              {sessionLoading ? "Loading account..." : session?.user.full_name ?? "Workspace account"}
            </p>
            <p className="mt-1 text-[11px] leading-none text-white/70">{subtitle}</p>
          </div>
        ) : null}
        {desktop ? (
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className={`h-4 w-4 text-white/72 transition ${open ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m5.5 7.75 4.5 4.5 4.5-4.5" />
          </svg>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          className={`absolute right-0 z-50 mt-3 w-[280px] overflow-hidden rounded-[22px] border border-white/12 bg-[linear-gradient(180deg,rgba(20,27,46,0.98),rgba(13,18,32,0.98))] p-2 shadow-[0_24px_64px_rgba(2,6,23,0.42)] backdrop-blur-xl ${
            desktop ? "" : "top-full"
          }`}
        >
          <div className="rounded-[18px] border border-white/8 bg-white/4 px-4 py-3 text-white">
            <p className="text-sm font-semibold">
              {session?.user.full_name ?? "Workspace account"}
            </p>
            <p className="mt-1 text-xs text-white/68">
              {session?.user.email ?? "Signed in"}
            </p>
            <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/52">
              {session?.organization.name ?? "Workspace"} · {subtitle}
            </p>
          </div>

          <div className="mt-2 space-y-1">
            <AccountMenuLink href="/live" label="Open live workspace" onNavigate={() => setOpen(false)} />
            <AccountMenuLink href="/control-center" label="Workspace settings" onNavigate={() => setOpen(false)} />
            <AccountMenuLink href="/onboarding" label="Project onboarding" onNavigate={() => setOpen(false)} />
          </div>

          <button
            type="button"
            onClick={() => void handleLogoutClick()}
            className="mt-2 flex w-full items-center justify-between rounded-[16px] px-4 py-3 text-left text-sm font-medium text-white/84 transition hover:bg-white/8"
          >
            <span>{isLoggingOut ? "Signing out..." : "Log out"}</span>
            <svg
              aria-hidden="true"
              viewBox="0 0 20 20"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M7 4.5h-1A2.5 2.5 0 0 0 3.5 7v6A2.5 2.5 0 0 0 6 15.5h1" />
              <path d="M11 6.5 15 10l-4 3.5" />
              <path d="M15 10H7.5" />
            </svg>
          </button>
        </div>
      ) : null}
    </div>
  );
}

function AccountMenuLink({
  href,
  label,
  onNavigate,
}: {
  href: string;
  label: string;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className="flex items-center justify-between rounded-[16px] px-4 py-3 text-sm font-medium text-white/84 transition hover:bg-white/8"
    >
      <span>{label}</span>
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M7.5 4.75 12.75 10 7.5 15.25" />
      </svg>
    </Link>
  );
}

function buildInitials(fullName?: string, email?: string) {
  const source = fullName?.trim() || email?.trim() || "S";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function readCurrentProjectCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie
    .split("; ")
    .find((value) => value.startsWith("stimpact_current_project="));
  if (!match) {
    return null;
  }
  const [, cookieValue] = match.split("=", 2);
  return cookieValue ? decodeURIComponent(cookieValue) : null;
}

function formatRole(role: AuthSession["role"]) {
  if (role === "owner") {
    return "Owner";
  }
  if (role === "admin") {
    return "Admin";
  }
  return "Member";
}

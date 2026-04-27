import Link from "next/link";

import {
  getCurrentSession,
  listWorkspaceAccessRequests,
  listWorkspaceInvites,
} from "@/lib/agent-platform";
import { WorkspaceAdminPanel } from "@/components/workspace-admin-panel";

export const dynamic = "force-dynamic";

export default async function WorkspaceSettingsPage() {
  const session = await getCurrentSession().catch(() => null);

  if (!session) {
    return (
      <main className="mx-auto max-w-[1120px] space-y-4 px-2 pb-12 pt-2">
        <h1 className="text-2xl font-bold text-white">Workspace settings</h1>
        <p className="max-w-lg text-sm text-white/65">
          Sign in to manage invites, access requests, and billing for your organization.
        </p>
        <Link
          href="/login"
          className="inline-flex rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white/85 transition hover:bg-white/[0.08]"
        >
          Sign in
        </Link>
      </main>
    );
  }

  const isAdmin = session.role === "owner" || session.role === "admin";
  const [invites, accessRequests] = isAdmin
    ? await Promise.all([
        listWorkspaceInvites(session.organization.id).catch(() => []),
        listWorkspaceAccessRequests(session.organization.id).catch(() => []),
      ])
    : [[], []];

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-12 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Workspace settings</h1>
          <p className="mt-1 text-sm text-white/50">
            Organization access, invites, and plan usage — not project automation policy.
          </p>
        </div>
        <Link
          href="/control-center"
          className="rounded-lg border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-white/80 transition hover:bg-white/[0.08]"
        >
          Control center
        </Link>
      </div>

      {isAdmin ? (
        <WorkspaceAdminPanel
          organizationId={session.organization.id}
          projectCount={session.projects.length}
          includedProjects={session.subscription?.included_projects ?? 1}
          additionalProjectPriceCents={session.subscription?.additional_project_price_cents ?? 0}
          invites={invites}
          accessRequests={accessRequests}
        />
      ) : (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-6 text-sm text-white/60">
          Only workspace <span className="text-white/85">owners</span> and{" "}
          <span className="text-white/85">admins</span> can create invites and approve access requests.
          Contact your administrator if you need a teammate added.
        </div>
      )}
    </main>
  );
}

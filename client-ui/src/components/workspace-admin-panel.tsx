"use client";

import { useState } from "react";

import type { AccessRequest, OrganizationInvite } from "@/lib/types";

type WorkspaceAdminPanelProps = {
  organizationId: string;
  projectCount: number;
  includedProjects: number;
  additionalProjectPriceCents: number;
  invites: OrganizationInvite[];
  accessRequests: AccessRequest[];
};

export function WorkspaceAdminPanel({
  organizationId,
  projectCount,
  includedProjects,
  additionalProjectPriceCents,
  invites: initialInvites,
  accessRequests: initialAccessRequests,
}: WorkspaceAdminPanelProps) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [invites, setInvites] = useState(initialInvites);
  const [accessRequests, setAccessRequests] = useState(initialAccessRequests);

  async function handleInviteSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    setInviteToken(null);
    try {
      const response = await fetch(`/api/auth/organizations/${organizationId}/invites`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: inviteEmail,
          role: "member",
        }),
      });
      const payload = (await response.json()) as
        | {
            invite: OrganizationInvite;
            invite_token: string;
          }
        | { error?: { message?: string } };
      if (!response.ok || !("invite" in payload)) {
        throw new Error(
          "error" in payload ? payload.error?.message ?? "Invite failed." : "Invite failed.",
        );
      }
      setInvites((current) => [payload.invite, ...current]);
      setInviteToken(payload.invite_token);
      setStatusMessage("Invite created. Share the token or append it to the signup URL.");
      setInviteEmail("");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Invite failed.");
    }
  }

  async function approveRequest(accessRequestId: string) {
    setStatusMessage(null);
    setErrorMessage(null);
    setInviteToken(null);
    try {
      const response = await fetch(
        `/api/auth/organizations/${organizationId}/access-requests/${accessRequestId}/approve`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            role: "member",
          }),
        },
      );
      const payload = (await response.json()) as
        | {
            invite: OrganizationInvite;
            invite_token: string;
            access_request: AccessRequest;
          }
        | { error?: { message?: string } };
      if (!response.ok || !("invite" in payload)) {
        throw new Error(
          "error" in payload
            ? payload.error?.message ?? "Approval failed."
            : "Approval failed.",
        );
      }
      setAccessRequests((current) =>
        current.map((request) =>
          request.id === accessRequestId ? payload.access_request : request,
        ),
      );
      setInvites((current) => [payload.invite, ...current]);
      setInviteToken(payload.invite_token);
      setStatusMessage("Access request approved. Share the invite token with the requester.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Approval failed.");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="space-y-4 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Billing</p>
          <h3 className="mt-2 text-lg font-semibold text-white">Project entitlement</h3>
          <p className="mt-2 text-sm text-white/55">
            {projectCount} active project{projectCount === 1 ? "" : "s"} · {includedProjects} included · +$
            {(additionalProjectPriceCents / 100).toFixed(0)}/mo per extra project.
          </p>
        </div>

        <form className="space-y-3" onSubmit={handleInviteSubmit}>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-white/75">Invite teammate</span>
            <input
              type="email"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="teammate@company.com"
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 text-sm text-white outline-none placeholder:text-white/35 focus:border-[#ff6a3d]/40"
              required
            />
          </label>
          <button
            type="submit"
            className="inline-flex rounded-lg bg-[#ff6a3d] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e85a30]"
          >
            Create invite
          </button>
        </form>

        {inviteToken ? (
          <div className="rounded-lg border border-[#2d7ff9]/25 bg-[#2d7ff9]/10 px-3 py-3 text-sm text-[#bfdbfe]">
            Invite token: <code className="text-white">{inviteToken}</code>
          </div>
        ) : null}

        {statusMessage ? (
          <div className="rounded-lg border border-[rgba(32,201,51,0.3)] bg-[rgba(32,201,51,0.1)] px-3 py-3 text-sm text-[#86efac]">
            {statusMessage}
          </div>
        ) : null}
        {errorMessage ? (
          <div className="rounded-lg border border-[rgba(248,113,113,0.35)] bg-[rgba(248,113,113,0.1)] px-3 py-3 text-sm text-[#fca5a5]">
            {errorMessage}
          </div>
        ) : null}
      </section>

      <section className="space-y-4 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Access</p>
          <h3 className="mt-2 text-lg font-semibold text-white">Requests & invites</h3>
        </div>

        <div className="space-y-2">
          {accessRequests.length === 0 ? (
            <p className="text-sm text-white/45">No pending access requests.</p>
          ) : (
            accessRequests.map((request) => (
              <div
                key={request.id}
                className="rounded-lg border border-white/10 bg-black/20 px-3 py-3"
              >
                <p className="font-medium text-white">{request.full_name}</p>
                <p className="mt-0.5 text-sm text-white/50">{request.email}</p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
                    {request.status}
                  </span>
                  {request.status === "pending" ? (
                    <button
                      type="button"
                      onClick={() => approveRequest(request.id)}
                      className="inline-flex rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-white/85 transition hover:bg-white/[0.1]"
                    >
                      Approve
                    </button>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2 border-t border-white/10 pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-white/40">Recent invites</p>
          {invites.length === 0 ? (
            <p className="text-sm text-white/45">None yet.</p>
          ) : (
            invites.slice(0, 5).map((invite) => (
              <div key={invite.id} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-[#93c5fd]">{invite.email}</span>
                <span className="text-white/45">{invite.status}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

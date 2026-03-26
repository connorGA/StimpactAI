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
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="space-y-4 rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-white px-5 py-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
            Workspace billing
          </p>
          <h3 className="mt-2 text-xl font-semibold text-[#171717]">
            Project-based access with unlimited seats
          </h3>
          <p className="mt-2 text-sm leading-6 text-[#746d66]">
            {projectCount} active project{projectCount === 1 ? "" : "s"} against {includedProjects} included. Additional projects bill at $
            {(additionalProjectPriceCents / 100).toFixed(0)} each per month.
          </p>
        </div>

        <form className="space-y-3" onSubmit={handleInviteSubmit}>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#171717]">Invite teammate</span>
            <input
              type="email"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="teammate@company.com"
              className="w-full rounded-[16px] border border-[rgba(17,24,39,0.12)] bg-white px-4 py-3 text-sm text-[#171717] outline-none transition focus:border-[rgba(52,81,209,0.42)]"
              required
            />
          </label>
          <button
            type="submit"
            className="inline-flex rounded-[16px] bg-[#17385d] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1f4a78]"
          >
            Create invite
          </button>
        </form>

        {inviteToken ? (
          <div className="rounded-[18px] bg-[#f8fbff] px-4 py-4 text-sm text-[#35547d]">
            Invite token: <code>{inviteToken}</code>
          </div>
        ) : null}

        {statusMessage ? (
          <div className="rounded-[18px] bg-[rgba(67,160,71,0.12)] px-4 py-3 text-sm text-[#2f6f35]">
            {statusMessage}
          </div>
        ) : null}
        {errorMessage ? (
          <div className="rounded-[18px] bg-[rgba(198,40,40,0.10)] px-4 py-3 text-sm text-[#8c2d2d]">
            {errorMessage}
          </div>
        ) : null}
      </section>

      <section className="space-y-4 rounded-[24px] border border-[rgba(17,24,39,0.08)] bg-white px-5 py-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a8178]">
            Access review
          </p>
          <h3 className="mt-2 text-xl font-semibold text-[#171717]">Requests and pending invites</h3>
        </div>

        <div className="space-y-3">
          {accessRequests.length === 0 ? (
            <p className="text-sm text-[#746d66]">No pending access requests.</p>
          ) : (
            accessRequests.map((request) => (
              <div
                key={request.id}
                className="rounded-[18px] border border-[rgba(17,24,39,0.08)] px-4 py-4"
              >
                <p className="font-medium text-[#171717]">{request.full_name}</p>
                <p className="mt-1 text-sm text-[#746d66]">{request.email}</p>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8a8178]">
                    {request.status}
                  </span>
                  {request.status === "pending" ? (
                    <button
                      type="button"
                      onClick={() => approveRequest(request.id)}
                      className="inline-flex rounded-full bg-[rgba(23,56,93,0.08)] px-3 py-2 text-xs font-semibold text-[#17385d] transition hover:bg-[rgba(23,56,93,0.14)]"
                    >
                      Approve
                    </button>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="space-y-3 border-t border-[rgba(17,24,39,0.08)] pt-4">
          <p className="text-sm font-semibold text-[#171717]">Recent invites</p>
          {invites.length === 0 ? (
            <p className="text-sm text-[#746d66]">No invites created yet.</p>
          ) : (
            invites.slice(0, 5).map((invite) => (
              <div key={invite.id} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-[#35547d]">{invite.email}</span>
                <span className="text-[#8a8178]">{invite.status}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

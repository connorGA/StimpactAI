import "server-only";

import { cookies } from "next/headers";

import { getCurrentSession } from "@/lib/agent-platform";

export const CURRENT_PROJECT_COOKIE = "stimpact_current_project";

export async function resolvePrimaryProjectId(): Promise<string | null> {
  const session = await getCurrentSession().catch(() => null);
  const selectedProjectId = (await cookies()).get(CURRENT_PROJECT_COOKIE)?.value ?? null;
  if (selectedProjectId && session?.projects.some((project) => project.id === selectedProjectId)) {
    return selectedProjectId;
  }
  return session?.projects[0]?.id ?? null;
}

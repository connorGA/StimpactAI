import "server-only";

import { getCurrentSession } from "@/lib/agent-platform";

export async function resolvePrimaryProjectId(): Promise<string | null> {
  const session = await getCurrentSession().catch(() => null);
  return session?.projects[0]?.id ?? null;
}

import "server-only";

import { getIncidents, listProviderIntegrations } from "@/lib/agent-platform";

export async function resolvePrimaryProjectId(): Promise<string | null> {
  const incidentList = await getIncidents({ limit: 1, offset: 0 }).catch(() => null);
  const incidentProjectId = incidentList?.items[0]?.project_id;
  if (incidentProjectId) {
    return incidentProjectId;
  }

  const integrations = await listProviderIntegrations().catch(() => []);
  for (const integration of integrations) {
    const projectId = integration.metadata.project_id;
    if (typeof projectId === "string" && projectId.trim()) {
      return projectId;
    }
  }

  return null;
}

export type IncidentStatus = "open" | "resolved";
export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type Environment = "production" | "staging" | "development" | "test";

export type IncidentSummary = {
  id: string;
  project_id: string;
  fingerprint: string;
  service: string;
  environment: Environment;
  title: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  first_seen_at: string;
  last_seen_at: string;
  event_count: number;
  latest_telemetry_id: string;
  created_at: string;
  updated_at: string;
};

export type IncidentEvent = {
  id: string;
  telemetry_id: string;
  event_type: string;
  error_message: string;
  stacktrace: string;
  request_payload: unknown;
  response_payload: unknown;
  payload: unknown;
  occurred_at: string;
  created_at: string;
};

export type IncidentListResponse = {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type IncidentDetailResponse = {
  incident: IncidentSummary;
  events: IncidentEvent[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type IncidentChatResponse = {
  answer: string;
  referenced_incident_ids: string[];
};

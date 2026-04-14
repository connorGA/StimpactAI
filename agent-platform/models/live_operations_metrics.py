from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveOperationsMetricsRecord:
    """Aggregated numbers for the live dashboard (computed in IncidentRepository)."""

    uptime_percent_last_30d: float
    uptime_percent_prior_30d: float
    avg_agent_response_seconds_last_30d: float | None
    avg_agent_response_seconds_prior_30d: float | None
    open_incidents: int
    agent_resolution_percent_last_30d: float | None
    agent_resolution_percent_prior_30d: float | None

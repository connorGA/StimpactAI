# Agent Platform

## Configuration

Set `AGENT_PLATFORM_TELEMETRY_CLASSIFIER_ENABLED=true` to enable telemetry classification before incident creation. It defaults to `false` so ingest continues to create incidents exactly as before during rollout. When enabled, ambiguous events can require human approval before autonomous repair, while clear user-error telemetry can be suppressed; tune the rollout with `OPENAI_TELEMETRY_CLASSIFIER_MODEL`, `AGENT_PLATFORM_TELEMETRY_CLASSIFIER_WINDOW_MINUTES`, and `AGENT_PLATFORM_TELEMETRY_CLASSIFIER_FREQUENCY_THRESHOLD`.

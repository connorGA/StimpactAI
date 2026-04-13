async function mintStimpactBrowserToken(req, res) {
  const baseUrl = process.env.STIMPACT_BASE_URL ?? process.env.NEXT_PUBLIC_STIMPACT_BASE_URL;
  const projectId = process.env.NEXT_PUBLIC_STIMPACT_PROJECT_ID ?? process.env.STIMPACT_PROJECT_ID;
  const browserTokenKey = process.env.STIMPACT_BROWSER_TOKEN_KEY;

  if (!baseUrl || !projectId || !browserTokenKey) {
    return res.status(500).json({
      error:
        "Missing Stimpact browser token route configuration. Set STIMPACT_BROWSER_TOKEN_KEY, STIMPACT_PROJECT_ID or NEXT_PUBLIC_STIMPACT_PROJECT_ID, and STIMPACT_BASE_URL or NEXT_PUBLIC_STIMPACT_BASE_URL.",
    });
  }

  const payload = typeof req.body === "object" && req.body !== null ? req.body : {};
  const service = typeof payload.service === "string" && payload.service.trim() ? payload.service.trim() : null;
  const environment =
    typeof payload.environment === "string" && payload.environment.trim()
      ? payload.environment.trim()
      : "production";
  const origin = typeof req.headers.origin === "string" ? req.headers.origin : null;

  if (!service || !origin) {
    return res.status(400).json({
      error: "A service value and same-origin browser request are required to mint a browser ingest token.",
    });
  }

  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/telemetry/browser-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      browser_key: browserTokenKey,
      service,
      environment,
      origin,
    }),
  });
  const parsed = await response.json().catch(() => null);
  return res.status(response.status).json(parsed ?? {});
}

function registerStimpactBrowserTokenRoute(app) {
  app.post("/api/stimpact-token", mintStimpactBrowserToken);
}

module.exports = { registerStimpactBrowserTokenRoute };

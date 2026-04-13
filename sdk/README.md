# Stimpact SDK

The TypeScript SDK sends runtime errors and heartbeats to the Stimpact agent platform.

Server runtimes should use a private project `apiKey`.

Browser runtimes should use either:

- a short-lived token flow via `browserKey`
- a custom `browserTokenEndpoint`
- a custom `tokenProvider`

## Capture contract

Stimpact treats error capture as two complementary layers:

- auto-capture for uncaught failures that escape to the runtime
- handled-error capture for failures your app catches intentionally

In practice that means:

- browser runtimes should enable `registerBrowserAutoCapture()` for `window` errors and unhandled promise rejections
- Node and other server runtimes should enable `registerProcessAutoCapture()` for uncaught exceptions and unhandled rejections
- handled errors inside `catch` blocks, request wrappers, mutation handlers, and framework callbacks should use `captureHandledError()`, `wrap()`, or `wrapAsync()`
- the SDK suppresses duplicate reporting for the same error object when a handled capture later reaches an auto-capture hook
- SDK transport failures are never recursively auto-captured as application errors

## Install

```sh
npm install @stimpact/sdk
```

For package release validation and the prepublish checklist, see `PUBLISH_VALIDATION.md`.

## Server usage

```ts
import { StimpactClient } from "@stimpact/sdk";

const stimpact = new StimpactClient({
  baseUrl: "https://your-stimpact-api.example.com",
  projectId: "billing-prod",
  apiKey: "stimp_live_...",
  service: "billing-api",
  environment: "production",
});

stimpact.registerProcessAutoCapture();

try {
  await doWork();
} catch (error) {
  await stimpact.captureHandledError({
    error,
    request: {
      method: "POST",
      url: "/api/charge",
    },
  });
}
```

## Browser usage

```ts
import { StimpactClient } from "@stimpact/sdk";

const stimpact = new StimpactClient({
  baseUrl: "https://your-stimpact-api.example.com",
  projectId: "billing-prod",
  browserKey: "stimp_browser_...",
  service: "billing-web",
  environment: "production",
  browserTokenFailureCooldownMs: 60_000,
});

stimpact.startHeartbeat({
  intervalMs: 300_000,
  jitterRatio: 0.1,
  skipWhenOffline: true,
});
stimpact.registerBrowserAutoCapture();
```

When you use `browserKey`, configure at least one deployed app origin for that specific key during onboarding. Stimpact keeps CORS broadly compatible across active browser-key origins so browser preflights can succeed, but the actual security boundary is the browser key's `allowed_origins` check during token exchange plus the ingest token's origin binding.

If you later revoke the key or remove an origin from its allowlist, new token exchanges from that origin fail and ingest re-checks the live browser-key record for defense in depth.

The SDK also applies a cooldown after non-retryable browser token failures such as invalid, revoked, or origin-blocked browser keys so it does not hammer `/telemetry/browser-token` on every subsequent error event.

For the strongest separation, use `browserTokenEndpoint` or `tokenProvider` so your app backend can mint short-lived ingest tokens without exposing any long-lived server credential to the browser.

## Heartbeats and live status

Use heartbeats as a lightweight "recently alive" signal, not a per-request health check.

- `sendHeartbeat()` sends one manual heartbeat immediately.
- `ping()` is an alias for `sendHeartbeat()` when you want a more explicit manual check-in call from UI code later.
- `startHeartbeat()` schedules periodic heartbeats with jitter and optional browser-aware pause behavior.

```ts
const heartbeat = stimpact.startHeartbeat({
  intervalMs: 5 * 60_000,
  jitterRatio: 0.1,
  skipWhenOffline: true,
  pauseWhenHidden: false,
});

await stimpact.ping();

// Manual dashboard-triggered check-in later:
await heartbeat.triggerNow({ commitSha: window.__APP_COMMIT_SHA__ });
```

For frontend apps, heartbeat freshness means "a real browser session for this app has checked in recently." It does not guarantee the site is globally up for every visitor when no browser session is active.

For server runtimes, heartbeats are a stronger liveness signal because they can run inside the long-lived process itself.

## Browser autocapture

```ts
const subscription = stimpact.registerBrowserAutoCapture();

// Later, if needed:
subscription.dispose();
```

The SDK ignores its own transport errors during browser auto-capture so a failed telemetry request does not recursively report itself as another browser error.

## Handled errors and framework integrations

Use handled-error capture anywhere your app intentionally catches and renders the failure instead of letting it escape globally.

```ts
try {
  await saveInvoice();
} catch (error) {
  await stimpact.captureHandledError({
    error,
    request: {
      method: "POST",
      url: "/api/invoices",
    },
  });
  throw error;
}
```

For synchronous code:

```ts
stimpact.wrap(() => {
  performDangerousSynchronousWork();
});
```

For async flows:

## Wrapped async flows

```ts
await stimpact.wrapAsync(async () => {
  await saveInvoice();
});
```

For framework-driven apps, instrument the shared boundary first instead of every component:

- request wrappers such as `fetch` helpers or API clients
- React Query / TanStack Query mutation and query defaults
- framework error boundaries, loaders, and action handlers

For example, a React Query mutation can capture the handled failure once in the shared `onError` path or request wrapper, then let the UI keep rendering the toast or retry state:

```ts
onError: async (error) => {
  await stimpact.captureHandledError({
    error,
    request: {
      method: "POST",
      url: "/requests",
    },
  });
  toast({ title: "Request failed" });
}
```

Avoid capturing the same failure in both a shared request wrapper and a component-level `onError` unless they are intentionally distinct telemetry events.

## Data minimization defaults

By default the SDK:

- sends the normalized error message and stacktrace
- does not forward request or response context unless you explicitly opt in
- redacts common sensitive headers such as `authorization`, `cookie`, `set-cookie`, and `x-api-key`
- omits request and response bodies unless `includeBodies` is enabled

To opt in to richer HTTP context:

```ts
const stimpact = new StimpactClient({
  baseUrl: "https://your-stimpact-api.example.com",
  projectId: "billing-prod",
  apiKey: "stimp_live_...",
  service: "billing-api",
  captureRequestContext: true,
  captureResponseContext: true,
  includeBodies: false,
});
```

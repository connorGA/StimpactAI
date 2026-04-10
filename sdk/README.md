# Stimpact SDK

The TypeScript SDK sends runtime errors and heartbeats to the Stimpact agent platform.

Server runtimes should use a private project `apiKey`.

Browser runtimes should use either:

- a short-lived token flow via `browserKey`
- a custom `browserTokenEndpoint`
- a custom `tokenProvider`

## Install

```sh
npm install @stimpact/sdk
```

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

try {
  await doWork();
} catch (error) {
  await stimpact.captureError({
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
});

stimpact.startHeartbeat();
stimpact.registerBrowserAutoCapture();
```

When you use `browserKey`, configure the deployed app origins that are allowed to exchange that key for a short-lived browser token. Stimpact checks both CORS and the browser key's `allowed_origins`, then binds the issued ingest token to the request origin.

For the strongest separation, use `browserTokenEndpoint` or `tokenProvider` so your app backend can mint short-lived ingest tokens without exposing any long-lived server credential to the browser.

## Browser autocapture

```ts
const subscription = stimpact.registerBrowserAutoCapture();

// Later, if needed:
subscription.dispose();
```

The SDK ignores its own transport errors during browser auto-capture so a failed telemetry request does not recursively report itself as another browser error.

## Wrapped async flows

```ts
await stimpact.wrapAsync(async () => {
  await saveInvoice();
});
```

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

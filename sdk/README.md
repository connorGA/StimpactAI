# Stimpact SDK

The TypeScript SDK sends runtime errors to the Stimpact agent platform using a project-scoped API key.

## Install

```sh
npm install @stimpact/sdk
```

## Basic usage

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

## Browser autocapture

```ts
const subscription = stimpact.registerBrowserAutoCapture();

// Later, if needed:
subscription.dispose();
```

## Wrapped async flows

```ts
await stimpact.wrapAsync(async () => {
  await saveInvoice();
});
```

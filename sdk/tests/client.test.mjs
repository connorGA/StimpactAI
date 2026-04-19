import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";

import { StimpactClient, StimpactRequestError } from "../dist/index.js";

test("captureError sends telemetry with project auth header", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await client.captureError({
    error: new Error("Database timeout"),
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://stimpact.example.com/telemetry/error");
  assert.equal(calls[0][1].headers["X-Stimpact-Project-Key"], "project-key");
});

test("captureError exchanges a browser key for a short-lived bearer token", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    browserKey: "stimp_browser_public",
    service: "billing-web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      if (String(url).endsWith("/telemetry/browser-token")) {
        return new Response(
          JSON.stringify({
            token: "browser-token-1",
            expires_in_seconds: 300,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await client.captureError({ error: new Error("boom") });

  assert.equal(calls.length, 2);
  assert.equal(calls[0][0], "https://stimpact.example.com/telemetry/browser-token");
  assert.equal(calls[1][0], "https://stimpact.example.com/telemetry/error");
  assert.equal(calls[1][1].headers.Authorization, "Bearer browser-token-1");
  assert.equal(calls[1][1].headers["X-Stimpact-Project-Key"], undefined);
});

test("browser token failures are cooled down after a non-retryable auth error", async () => {
  let attempts = 0;
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    browserKey: "stimp_browser_public",
    service: "billing-web",
    retryAttempts: 0,
    browserTokenFailureCooldownMs: 60_000,
    fetchImpl: async (url) => {
      if (String(url).endsWith("/telemetry/browser-token")) {
        attempts += 1;
        return new Response(JSON.stringify({ error: "forbidden" }), { status: 403 });
      }
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await assert.rejects(
    client.captureError({ error: new Error("boom-1") }),
    (error) =>
      error instanceof StimpactRequestError &&
      error.status === 403 &&
      error.retryable === false,
  );

  await assert.rejects(
    client.captureError({ error: new Error("boom-2") }),
    (error) =>
      error instanceof StimpactRequestError &&
      error.status === 403 &&
      error.retryable === false,
  );

  assert.equal(attempts, 1);
});

test("captureError retries transient failures and throws on repeated non-2xx", async () => {
  let attempts = 0;
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    retryAttempts: 2,
    retryDelayMs: 1,
    fetchImpl: async () => {
      attempts += 1;
      return new Response("upstream unavailable", { status: 503 });
    },
  });

  await assert.rejects(
    client.captureError({ error: "boom" }),
    (error) =>
      error instanceof StimpactRequestError &&
      error.status === 503 &&
      error.retryable === true,
  );
  assert.equal(attempts, 3);
});

test("wrapAsync preserves the original error when telemetry capture fails", async () => {
  const original = new Error("operation failed");
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    retryAttempts: 0,
    fetchImpl: async () => {
      throw new Error("network down");
    },
  });

  await assert.rejects(
    client.wrapAsync(async () => {
      throw original;
    }),
    (error) => error === original,
  );
  assert.ok(original.captureFailure instanceof Error);
});

test("browser auto-capture ignores SDK transport errors", async () => {
  const listeners = new Map();
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type) {
      listeners.delete(type);
    },
  };

  let attempts = 0;
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    fetchImpl: async () => {
      attempts += 1;
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  try {
    const subscription = client.registerBrowserAutoCapture();
    listeners.get("unhandledrejection")?.({
      reason: new StimpactRequestError("Request failed before the platform acknowledged it.", {
        retryable: true,
      }),
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    subscription.dispose();
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(attempts, 0);
});

test("browser auto-capture forwards window errors", async () => {
  const listeners = new Map();
  const calls = [];
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type) {
      listeners.delete(type);
    },
  };

  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  try {
    const subscription = client.registerBrowserAutoCapture();
    listeners.get("error")?.({
      error: new Error("render boom"),
      message: "render boom",
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    subscription.dispose();
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(calls.length, 1);
  const payload = JSON.parse(calls[0][1].body);
  assert.equal(payload.error_message, "render boom");
  assert.match(payload.stacktrace, /render boom/);
});

test("captureHandledError avoids duplicate browser auto-capture for the same error object", async () => {
  const listeners = new Map();
  const calls = [];
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type) {
      listeners.delete(type);
    },
  };

  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });
  const sharedError = new Error("mutation failed");

  try {
    const subscription = client.registerBrowserAutoCapture();
    await client.captureHandledError({ error: sharedError });
    listeners.get("unhandledrejection")?.({
      reason: sharedError,
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    subscription.dispose();
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(calls.length, 1);
});

test("wrap captures synchronous handled errors and rethrows the original error", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });
  const original = new Error("sync failure");

  assert.throws(
    () =>
      client.wrap(() => {
        throw original;
      }),
    (error) => error === original,
  );
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(calls.length, 1);
  const payload = JSON.parse(calls[0][1].body);
  assert.equal(payload.error_message, "sync failure");
});

test("process auto-capture forwards uncaught exceptions and unhandled rejections", async () => {
  const calls = [];
  const processTarget = new EventEmitter();
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  const subscription = client.registerProcessAutoCapture({ processTarget });
  processTarget.emit("uncaughtException", new Error("uncaught boom"));
  processTarget.emit("unhandledRejection", new Error("async boom"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  subscription.dispose();
  processTarget.emit("uncaughtException", new Error("ignored after dispose"));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(calls.length, 2);
  const payloads = calls.map(([, init]) => JSON.parse(init.body));
  assert.deepEqual(
    payloads.map((payload) => payload.error_message),
    ["uncaught boom", "async boom"],
  );
});

test("sendHeartbeat posts to the heartbeat endpoint", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await client.sendHeartbeat({ commitSha: "abc123" });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://stimpact.example.com/telemetry/heartbeat");
  const payload = JSON.parse(calls[0][1].body);
  assert.equal(payload.project_id, "project-1");
  assert.equal(payload.service, "billing-web");
  assert.equal(payload.commit_sha, "abc123");
});

test("heartbeat scheduler supports pause, resume, and manual trigger", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  const subscription = client.startHeartbeat({
    intervalMs: 50,
    immediate: false,
    jitterRatio: 0,
  });

  try {
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.equal(calls.length, 1);
    assert.equal(subscription.isRunning(), true);

    subscription.pause();
    assert.equal(subscription.isRunning(), false);
    const pausedCount = calls.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.equal(calls.length, pausedCount);

    await subscription.triggerNow({ commitSha: "manual-check" });
    assert.equal(calls.length, pausedCount + 1);
    assert.equal(JSON.parse(calls.at(-1)[1].body).commit_sha, "manual-check");

    subscription.resume();
    assert.equal(subscription.isRunning(), true);
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.ok(calls.length >= pausedCount + 2);
  } finally {
    subscription.dispose();
  }
});

test("request and response context are redacted and omitted by default", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await client.captureError({
    error: new Error("Database timeout"),
    request: {
      method: "POST",
      url: "https://app.example.com/api/charge",
      headers: {
        authorization: "Bearer secret",
      },
      body: {
        cardNumber: "4111111111111111",
      },
    },
    response: {
      status_code: 503,
      headers: {
        "set-cookie": "session=secret",
      },
      body: "response body",
    },
  });

  const payload = JSON.parse(calls[0][1].body);
  assert.equal(payload.request, undefined);
  assert.equal(payload.response, undefined);
});

test("opt-in HTTP context capture redacts headers and excludes bodies unless enabled", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-api",
    captureRequestContext: true,
    captureResponseContext: true,
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });

  await client.captureError({
    error: { message: "boom", nested: { token: "secret" } },
    request: {
      method: "POST",
      url: "https://app.example.com/api/charge",
      headers: {
        authorization: "Bearer secret",
        "x-request-id": "abc123",
      },
      body: {
        cardNumber: "4111111111111111",
      },
    },
    response: {
      status_code: 503,
      headers: {
        "set-cookie": "session=secret",
        "content-type": "application/json",
      },
      body: "response body",
    },
  });

  const payload = JSON.parse(calls[0][1].body);
  assert.deepEqual(payload.request.headers, {
    authorization: "[REDACTED]",
    "x-request-id": "abc123",
  });
  assert.equal(payload.request.body, undefined);
  assert.deepEqual(payload.response.headers, {
    "set-cookie": "[REDACTED]",
    "content-type": "application/json",
  });
  assert.equal(payload.response.body, undefined);
  assert.match(payload.stacktrace, /boom/);
});

test("captureError forwards user, tags, breadcrumbs, release, and session metadata", async () => {
  const calls = [];
  const client = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "project-1",
    apiKey: "project-key",
    service: "billing-web",
    release: "billing-web@1.2.3",
    dist: "web",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    },
  });
  client.setUser({ id: "user-123", email: "hello@example.com" });
  client.setTags({ tenant: "acme" });
  client.setContext("build", { commit: "abc123" });
  client.addBreadcrumb({
    category: "ui.click",
    message: "button#save",
    level: "info",
  });

  await client.captureHandledError({
    error: new Error("save failed"),
    tags: { screen: "checkout" },
  });

  const payload = JSON.parse(calls[0][1].body);
  assert.equal(payload.release, "billing-web@1.2.3");
  assert.equal(payload.dist, "web");
  assert.equal(payload.user.id, "user-123");
  assert.equal(payload.tags.tenant, "acme");
  assert.equal(payload.tags.screen, "checkout");
  assert.equal(payload.contexts.build.commit, "abc123");
  assert.equal(Array.isArray(payload.breadcrumbs), true);
  assert.equal(payload.breadcrumbs[0].category, "ui.click");
});

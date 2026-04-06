import test from "node:test";
import assert from "node:assert/strict";

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

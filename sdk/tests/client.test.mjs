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

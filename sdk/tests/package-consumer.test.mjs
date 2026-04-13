import test from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sdkDir = path.resolve(__dirname, "..");
const fixtureDir = path.join(__dirname, "fixtures", "vite-react-consumer");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

function npm(args, cwd) {
  return execFileSync(npmCommand, args, {
    cwd,
    encoding: "utf-8",
    stdio: "pipe",
  }).trim();
}

function packSdk(tempRoot) {
  const output = npm(["pack", "--pack-destination", tempRoot], sdkDir);
  const tarballName = output.split(/\r?\n/).pop()?.trim();
  assert.ok(tarballName, "npm pack did not return a tarball name");
  return path.join(tempRoot, tarballName);
}

function inspectPackFileList() {
  const output = npm(["pack", "--dry-run", "--json"], sdkDir);
  const parsed = JSON.parse(output);
  assert.ok(Array.isArray(parsed) && parsed.length > 0, "npm pack --json did not return a file list");
  const packedFiles = new Set(parsed[0].files.map((entry) => entry.path));
  assert.ok(packedFiles.has("dist/client.js"));
  assert.ok(packedFiles.has("dist/index.d.ts"));
  assert.ok(packedFiles.has("README.md"));
}

function prepareConsumer(tempRoot, tarballPath) {
  const consumerDir = path.join(tempRoot, "consumer");
  cpSync(fixtureDir, consumerDir, { recursive: true });
  const packageJsonPath = path.join(consumerDir, "package.json");
  const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf-8"));
  packageJson.dependencies["@stimpact/sdk"] = `file:${tarballPath}`;
  writeFileSync(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`, "utf-8");
  return consumerDir;
}

function verifyPackedRuntime(consumerDir) {
  const scriptPath = path.join(consumerDir, "verify-sdk-runtime.mjs");
  writeFileSync(
    scriptPath,
    `import assert from "node:assert/strict";
import { StimpactClient } from "@stimpact/sdk";

assert.equal(typeof StimpactClient.prototype.captureHandledError, "function");
assert.equal(typeof StimpactClient.prototype.wrap, "function");
assert.equal(typeof StimpactClient.prototype.wrapAsync, "function");
assert.equal(typeof StimpactClient.prototype.registerProcessAutoCapture, "function");

const calls = [];
const client = new StimpactClient({
  baseUrl: "https://stimpact.example.com",
  projectId: "project-1",
  apiKey: "stimp_live_fixture",
  service: "fixture-web",
  fetchImpl: async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
  },
});

await client.captureHandledError({ error: new Error("fixture handled error") });
assert.equal(calls.length, 1);
const payload = JSON.parse(calls[0][1].body);
assert.equal(payload.error_message, "fixture handled error");
`,
    "utf-8",
  );
  execFileSync(process.execPath, [scriptPath], {
    cwd: consumerDir,
    stdio: "pipe",
  });
}

function verifyPackagedBrowserIntegrationRuntime(consumerDir) {
  const scriptPath = path.join(consumerDir, "verify-browser-integration-runtime.mjs");
  writeFileSync(
    scriptPath,
    `import assert from "node:assert/strict";
import { StimpactClient, StimpactRequestError } from "@stimpact/sdk";

const telemetryCalls = [];
const listeners = new Map();
const originalWindow = globalThis.window;
const originalFetch = globalThis.fetch;

globalThis.window = {
  addEventListener(type, listener) {
    listeners.set(type, listener);
  },
  removeEventListener(type) {
    listeners.delete(type);
  },
};

const telemetryClient = new StimpactClient({
  baseUrl: "https://stimpact.example.com",
  projectId: "fixture-project",
  apiKey: "stimp_live_fixture",
  service: "fixture-web",
  captureRequestContext: true,
  captureResponseContext: true,
  fetchImpl: async (url, init) => {
    telemetryCalls.push([url, init]);
    return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
  },
});

async function captureHandledError(input) {
  await telemetryClient.captureHandledError(input);
}

function wrapStimpact(operation, context) {
  return telemetryClient.wrap(operation, context);
}

async function wrapStimpactAsync(operation, context) {
  return await telemetryClient.wrapAsync(operation, context);
}

async function requestExample(endpoint) {
  const method = "POST";
  try {
    const response = await fetch(endpoint, { method });
    if (!response.ok) {
      const error = new Error(\`\${response.status}: \${response.statusText}\`);
      await captureHandledError({
        error,
        request: { method, url: endpoint },
        response: { status_code: response.status },
      });
      throw error;
    }
    return response;
  } catch (error) {
    await captureHandledError({
      error,
      request: { method, url: endpoint },
    });
    throw error;
  }
}

function describeReactQueryKey(key) {
  if (!key || key.length === 0) {
    return "react-query";
  }
  return key.map((segment) => String(segment)).join("/");
}

async function tick() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

try {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ error: "downstream unavailable" }), {
      status: 503,
      statusText: "Service Unavailable",
    });

  await assert.rejects(
    requestExample("/requests"),
    (error) => error instanceof Error && error.message === "503: Service Unavailable",
  );
  assert.equal(telemetryCalls.length, 1);
  let payload = JSON.parse(telemetryCalls[0][1].body);
  assert.equal(payload.error_message, "503: Service Unavailable");
  assert.equal(payload.request.method, "POST");
  assert.equal(payload.request.url, "/requests");
  assert.equal(payload.response.status_code, 503);

  const queryError = new Error("query failed");
  await captureHandledError({
    error: queryError,
    request: { method: "QUERY", url: describeReactQueryKey(["orders", "list"]) },
  });
  assert.equal(telemetryCalls.length, 2);
  payload = JSON.parse(telemetryCalls[1][1].body);
  assert.equal(payload.error_message, "query failed");
  assert.equal(payload.request.method, "QUERY");
  assert.equal(payload.request.url, "orders/list");

  let toastCount = 0;
  const mutationError = new Error("mutation failed");
  await captureHandledError({
    error: mutationError,
    request: { method: "MUTATION", url: describeReactQueryKey(["requests", "create"]) },
  });
  toastCount += 1;
  assert.equal(toastCount, 1);
  assert.equal(telemetryCalls.length, 3);
  payload = JSON.parse(telemetryCalls[2][1].body);
  assert.equal(payload.error_message, "mutation failed");
  assert.equal(payload.request.method, "MUTATION");
  assert.equal(payload.request.url, "requests/create");

  const syncError = new Error("sync failure");
  assert.throws(
    () =>
      wrapStimpact(() => {
        throw syncError;
      }),
    (error) => error === syncError,
  );
  await tick();
  assert.equal(telemetryCalls.length, 4);
  payload = JSON.parse(telemetryCalls[3][1].body);
  assert.equal(payload.error_message, "sync failure");

  const asyncError = new Error("async failure");
  await assert.rejects(
    wrapStimpactAsync(async () => {
      throw asyncError;
    }),
    (error) => error === asyncError,
  );
  assert.equal(telemetryCalls.length, 5);
  payload = JSON.parse(telemetryCalls[4][1].body);
  assert.equal(payload.error_message, "async failure");

  const autocapture = telemetryClient.registerBrowserAutoCapture();
  const sharedError = new Error("shared handled browser error");
  await captureHandledError({
    error: sharedError,
    request: { method: "POST", url: "/shared" },
  });
  listeners.get("unhandledrejection")?.({ reason: sharedError });
  await tick();
  assert.equal(telemetryCalls.length, 6);
  payload = JSON.parse(telemetryCalls[5][1].body);
  assert.equal(payload.error_message, "shared handled browser error");

  listeners.get("error")?.({
    error: new Error("uncaught render boom"),
    message: "uncaught render boom",
  });
  await tick();
  assert.equal(telemetryCalls.length, 7);
  payload = JSON.parse(telemetryCalls[6][1].body);
  assert.equal(payload.error_message, "uncaught render boom");

  listeners.get("unhandledrejection")?.({
    reason: new StimpactRequestError("Request failed before the platform acknowledged it.", {
      retryable: true,
    }),
  });
  await tick();
  assert.equal(telemetryCalls.length, 7);

  autocapture.dispose();
} finally {
  globalThis.window = originalWindow;
  globalThis.fetch = originalFetch;
}
`,
    "utf-8",
  );
  execFileSync(process.execPath, [scriptPath], {
    cwd: consumerDir,
    stdio: "pipe",
  });
}

test("packed SDK tarball installs and builds in a Vite React consumer", () => {
  const tempRoot = path.join(os.tmpdir(), `stimpact-sdk-consumer-${Date.now()}`);
  mkdirSync(tempRoot, { recursive: true });
  try {
    inspectPackFileList();
    const tarballPath = packSdk(tempRoot);
    const consumerDir = prepareConsumer(tempRoot, tarballPath);
    npm(["install"], consumerDir);
    verifyPackedRuntime(consumerDir);
    verifyPackagedBrowserIntegrationRuntime(consumerDir);
    npm(["run", "build"], consumerDir);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

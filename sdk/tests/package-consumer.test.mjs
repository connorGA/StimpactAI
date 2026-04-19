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
  assert.ok(packedFiles.has("dist/next.js"));
  assert.ok(packedFiles.has("dist/vite.js"));
  assert.ok(packedFiles.has("dist/react.js"));
  assert.ok(packedFiles.has("dist/node.js"));
  assert.ok(packedFiles.has("dist/react-query.js"));
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
import { installStimpact as installNodeStimpact } from "@stimpact/sdk/node";
import { wrapQueryClient } from "@stimpact/sdk/react-query";

assert.equal(typeof StimpactClient.prototype.captureHandledError, "function");
assert.equal(typeof StimpactClient.prototype.wrap, "function");
assert.equal(typeof StimpactClient.prototype.wrapAsync, "function");
assert.equal(typeof StimpactClient.prototype.registerProcessAutoCapture, "function");
assert.equal(typeof installNodeStimpact, "function");
assert.equal(typeof wrapQueryClient, "function");

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
import {
  captureHandledError,
  getStimpactClient,
  installStimpact,
  wrapStimpact,
  wrapStimpactAsync,
} from "@stimpact/sdk/vite";
import { wrapQueryClient } from "@stimpact/sdk/react-query";

assert.equal(typeof installStimpact, "function");
assert.equal(typeof captureHandledError, "function");
assert.equal(typeof getStimpactClient, "function");
assert.equal(typeof wrapStimpact, "function");
assert.equal(typeof wrapStimpactAsync, "function");
assert.equal(typeof wrapQueryClient, "function");

const queryClient = {
  defaultOptions: {},
  getDefaultOptions() {
    return this.defaultOptions;
  },
  setDefaultOptions(options) {
    this.defaultOptions = options;
  },
};

const wrapped = wrapQueryClient(queryClient);
assert.equal(wrapped, queryClient);
assert.equal(typeof queryClient.defaultOptions.queries.onError, "function");
assert.equal(typeof queryClient.defaultOptions.mutations.onError, "function");
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

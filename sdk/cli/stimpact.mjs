#!/usr/bin/env node

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

function usage() {
  console.error(
    "Usage: stimpact sourcemaps upload --project <id> --release <release> [--dist <dist>] --base-url <url> --token <token> <dir>",
  );
  process.exit(1);
}

function readFlag(name, args) {
  const index = args.indexOf(name);
  if (index === -1 || index === args.length - 1) {
    return null;
  }
  return args[index + 1];
}

async function collectMapFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const output = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      output.push(...(await collectMapFiles(fullPath)));
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".map")) {
      output.push(fullPath);
    }
  }
  return output;
}

async function uploadSourcemaps(args) {
  const project = readFlag("--project", args);
  const release = readFlag("--release", args);
  const dist = readFlag("--dist", args);
  const baseUrl = readFlag("--base-url", args);
  const token = readFlag("--token", args);
  const targetDir = args.at(-1);
  if (!project || !release || !baseUrl || !token || !targetDir || targetDir.startsWith("--")) {
    usage();
  }

  const mapFiles = await collectMapFiles(path.resolve(targetDir));
  if (mapFiles.length === 0) {
    throw new Error(`No .map files found under ${targetDir}`);
  }

  const form = new FormData();
  for (const filePath of mapFiles) {
    const contents = await readFile(filePath);
    const relativePath = path.relative(path.resolve(targetDir), filePath);
    form.append("files", new Blob([contents], { type: "application/json" }), relativePath);
  }

  const params = new URLSearchParams();
  if (dist) {
    params.set("dist", dist);
  }
  const response = await fetch(
    `${baseUrl.replace(/\/$/, "")}/control-plane/projects/${project}/releases/${encodeURIComponent(release)}/sourcemaps?${params.toString()}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: form,
    },
  );

  if (!response.ok) {
    throw new Error(`Sourcemap upload failed with status ${response.status}: ${await response.text()}`);
  }
  const result = await response.json();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const [, , command, subcommand, ...args] = process.argv;
if (command === "sourcemaps" && subcommand === "upload") {
  await uploadSourcemaps(args);
} else {
  usage();
}

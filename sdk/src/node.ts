import { StimpactClient } from "./client.js";
import type { StimpactEnvironment } from "./types.js";

export type NodeHandledErrorInput = Parameters<StimpactClient["captureHandledError"]>[0];
export type NodeHandledErrorContext = Omit<NodeHandledErrorInput, "error">;

let installed = false;
let stimpactClient: StimpactClient | null = null;
const handledErrors = new WeakSet<object>();

export function getStimpactClient(): StimpactClient | null {
  return stimpactClient;
}

export async function pingStimpact(): Promise<void> {
  if (!stimpactClient) {
    return;
  }
  await stimpactClient.ping();
}

export async function captureHandledError(input: NodeHandledErrorInput): Promise<void> {
  if (!stimpactClient) {
    return;
  }
  const trackedError =
    (typeof input.error === "object" && input.error !== null) || typeof input.error === "function"
      ? (input.error as object)
      : null;
  if (trackedError && handledErrors.has(trackedError)) {
    return;
  }
  if (trackedError) {
    handledErrors.add(trackedError);
  }
  try {
    await stimpactClient.captureHandledError(input);
  } catch (error) {
    if (trackedError) {
      handledErrors.delete(trackedError);
    }
    throw error;
  }
}

export function wrapStimpact<T>(operation: () => T, context?: NodeHandledErrorContext): T {
  if (!stimpactClient) {
    return operation();
  }
  return stimpactClient.wrap(operation, context);
}

export async function wrapStimpactAsync<T>(
  operation: () => Promise<T>,
  context?: NodeHandledErrorContext,
): Promise<T> {
  if (!stimpactClient) {
    return await operation();
  }
  return await stimpactClient.wrapAsync(operation, context);
}

export function installStimpact(options: {
  service?: string;
  environment?: StimpactEnvironment;
} = {}): StimpactClient | null {
  if (installed) {
    return stimpactClient;
  }
  installed = true;
  const baseUrl = process.env.STIMPACT_BASE_URL;
  const projectId = process.env.STIMPACT_PROJECT_ID;
  const apiKey = process.env.STIMPACT_API_KEY;
  if (!baseUrl || !projectId || !apiKey) {
    return null;
  }
  const client = new StimpactClient({
    baseUrl,
    projectId,
    apiKey,
    service: options.service ?? process.env.STIMPACT_SERVICE ?? "server",
    environment: options.environment ?? ((process.env.STIMPACT_ENVIRONMENT as StimpactEnvironment | undefined) ?? "production"),
  });
  stimpactClient = client;
  client.startHeartbeat();
  client.registerProcessAutoCapture();
  return client;
}

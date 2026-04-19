import { StimpactClient } from "./client.js";
import type { StimpactEnvironment } from "./types.js";

export type HandledErrorInput = Parameters<StimpactClient["captureHandledError"]>[0];
export type HandledErrorContext = Omit<HandledErrorInput, "error">;

export type BrowserRuntimeOptions = {
  baseUrl?: string | null;
  projectId?: string | null;
  browserKey?: string | null;
  service: string;
  environment: StimpactEnvironment;
};

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

export async function captureHandledError(input: HandledErrorInput): Promise<void> {
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

export function wrapStimpact<T>(operation: () => T, context?: HandledErrorContext): T {
  if (!stimpactClient) {
    return operation();
  }
  return stimpactClient.wrap(operation, context);
}

export async function wrapStimpactAsync<T>(
  operation: () => Promise<T>,
  context?: HandledErrorContext,
): Promise<T> {
  if (!stimpactClient) {
    return await operation();
  }
  return await stimpactClient.wrapAsync(operation, context);
}

export function installBrowserRuntime(options: BrowserRuntimeOptions): StimpactClient | null {
  if (installed) {
    return stimpactClient;
  }
  installed = true;
  const runtime = startBrowserRuntime(options);
  return runtime.client;
}

export function startBrowserRuntime(
  options: BrowserRuntimeOptions,
): { client: StimpactClient | null; dispose: () => void } {
  const { baseUrl, projectId, browserKey, service, environment } = options;
  if (!baseUrl || !projectId || !browserKey || !service) {
    return { client: null, dispose: () => undefined };
  }

  const client = new StimpactClient({
    baseUrl,
    projectId,
    browserKey,
    service,
    environment,
  });
  stimpactClient = client;
  syncWindowStimpactControls();

  const heartbeat = client.startHeartbeat();
  const subscription = client.registerBrowserAutoCapture();

  return {
    client,
    dispose: () => {
      heartbeat.dispose();
      subscription.dispose();
      if (stimpactClient === client) {
        stimpactClient = null;
        syncWindowStimpactControls();
      }
    },
  };
}

function syncWindowStimpactControls(): void {
  if (typeof window === "undefined") {
    return;
  }
  const scope = window as Window & {
    __stimpact?: {
      ping: typeof pingStimpact;
      getClient: typeof getStimpactClient;
      captureHandledError: typeof captureHandledError;
    };
    pingStimpact?: typeof pingStimpact;
  };
  if (stimpactClient) {
    scope.pingStimpact = pingStimpact;
    scope.__stimpact = {
      ping: pingStimpact,
      getClient: getStimpactClient,
      captureHandledError,
    };
    return;
  }
  if (scope.pingStimpact === pingStimpact) {
    delete scope.pingStimpact;
  }
  if (scope.__stimpact?.ping === pingStimpact) {
    delete scope.__stimpact;
  }
}

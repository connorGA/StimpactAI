import { StimpactClient } from "@stimpact/sdk";

let installed = false;
let stimpactClient: StimpactClient | null = null;
type HandledErrorInput = Parameters<StimpactClient["captureError"]>[0];
type HandledErrorContext = Omit<HandledErrorInput, "error">;
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
    const runtimeClient = stimpactClient as StimpactClient & {
      captureHandledError?: (payload: HandledErrorInput) => Promise<void>;
      captureError: (payload: HandledErrorInput) => Promise<void>;
    };
    if (typeof runtimeClient.captureHandledError === "function") {
      await runtimeClient.captureHandledError(input);
      return;
    }
    await runtimeClient.captureError(input);
  } catch (error) {
    if (trackedError) {
      handledErrors.delete(trackedError);
    }
    throw error;
  }
}

export function wrapStimpact<T>(
  operation: () => T,
  context?: HandledErrorContext,
): T {
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

function syncWindowStimpactControls() {
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

export function installStimpact() {
  if (installed) {
    return;
  }
  installed = true;

  const baseUrl = import.meta.env.VITE_STIMPACT_BASE_URL;
  const projectId = import.meta.env.VITE_STIMPACT_PROJECT_ID;
  const browserKey = import.meta.env.VITE_STIMPACT_BROWSER_KEY;
  const service = "Soul Song Service";
  const runtimeEnvironment = "production";

  if (!baseUrl || !projectId || !browserKey || !service) {
    return;
  }

  const client = new StimpactClient({
    baseUrl,
    projectId,
    browserKey,
    service,
    environment: runtimeEnvironment,
  });
  stimpactClient = client;
  syncWindowStimpactControls();

  client.startHeartbeat();
  client.registerBrowserAutoCapture();
}

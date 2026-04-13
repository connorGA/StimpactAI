import { StimpactClient } from "@stimpact/sdk";

let installed = false;
let stimpactClient: StimpactClient | null = null;

type HandledErrorInput = Parameters<StimpactClient["captureHandledError"]>[0];
type HandledErrorContext = Omit<HandledErrorInput, "error">;

export function getStimpactClient(): StimpactClient | null {
  return stimpactClient;
}

export async function captureHandledError(input: HandledErrorInput): Promise<void> {
  if (!stimpactClient) {
    return;
  }
  await stimpactClient.captureHandledError(input);
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

export function installStimpact() {
  if (installed) {
    return;
  }
  installed = true;
  stimpactClient = new StimpactClient({
    baseUrl: "https://stimpact.example.com",
    projectId: "fixture-project",
    browserKey: "stimp_browser_fixture",
    service: "fixture-web",
    environment: "production",
  });
  stimpactClient.startHeartbeat();
  stimpactClient.registerBrowserAutoCapture();
}

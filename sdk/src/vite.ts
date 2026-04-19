import {
  captureHandledError,
  getStimpactClient,
  installBrowserRuntime,
  pingStimpact,
  wrapStimpact,
  wrapStimpactAsync,
} from "./browser-runtime.js";
import type { StimpactEnvironment } from "./types.js";

export { captureHandledError, getStimpactClient, pingStimpact, wrapStimpact, wrapStimpactAsync };

export function installStimpact(options: {
  service?: string;
  environment?: StimpactEnvironment;
} = {}) {
  return installBrowserRuntime({
    baseUrl: import.meta.env.VITE_STIMPACT_BASE_URL,
    projectId: import.meta.env.VITE_STIMPACT_PROJECT_ID,
    browserKey: import.meta.env.VITE_STIMPACT_BROWSER_KEY,
    service: options.service ?? "web",
    environment: options.environment ?? "production",
  });
}

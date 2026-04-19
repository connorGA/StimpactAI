import { useEffect } from "react";

import {
  captureHandledError,
  getStimpactClient,
  pingStimpact,
  startBrowserRuntime,
  wrapStimpact,
  wrapStimpactAsync,
} from "./browser-runtime.js";

export { captureHandledError, getStimpactClient, pingStimpact, wrapStimpact, wrapStimpactAsync };

export function StimpactProvider(props: {
  service?: string;
  environment?: "production" | "staging" | "development" | "test";
} = {}): null {
  useEffect(() => {
    const runtime = startBrowserRuntime({
      baseUrl: process.env.NEXT_PUBLIC_STIMPACT_BASE_URL,
      projectId: process.env.NEXT_PUBLIC_STIMPACT_PROJECT_ID,
      browserKey: process.env.NEXT_PUBLIC_STIMPACT_BROWSER_KEY,
      service: props.service ?? "web",
      environment: props.environment ?? "production",
    });
    return () => {
      runtime.dispose();
    };
  }, [props.environment, props.service]);

  return null;
}

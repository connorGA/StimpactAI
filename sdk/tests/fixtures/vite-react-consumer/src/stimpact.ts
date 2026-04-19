import {
  captureHandledError,
  getStimpactClient,
  installStimpact as installViteStimpact,
  wrapStimpact,
  wrapStimpactAsync,
} from "@stimpact/sdk/vite";

export { captureHandledError, getStimpactClient, wrapStimpact, wrapStimpactAsync };

export function installStimpact() {
  installViteStimpact({
    service: "fixture-web",
    environment: "production",
  });
}

# SDK Publish Validation

Use this checklist before publishing a new `@stimpact/sdk` version.

## Consumer Validation Matrix

| Surface | What to prove | Validation |
| --- | --- | --- |
| Package tarball | Published artifact contains the expected runtime and type files | `npm --prefix sdk run pack:dry-run` and inspect `dist/client.js`, `dist/index.d.ts`, and `README.md` |
| Runtime SDK API | The packaged SDK exposes `captureHandledError()`, `wrap()`, `wrapAsync()`, and `registerProcessAutoCapture()` at runtime | `npm --prefix sdk run test:consumer` |
| Browser helper contract | A browser helper can call `captureHandledError()` directly without generator-side fallbacks | `sdk/tests/fixtures/vite-react-consumer/src/stimpact.ts` compiled by `npm --prefix sdk run test:consumer` |
| React Query handled failures | Shared query and mutation boundaries can capture handled failures while UI `onError` callbacks continue rendering toasts | `sdk/tests/fixtures/vite-react-consumer/src/lib/queryClient.ts` compiled by `npm --prefix sdk run test:consumer` |
| Shared request wrappers | Request wrappers can capture handled failures with request and response context | `sdk/tests/fixtures/vite-react-consumer/src/lib/requestClient.ts` compiled by `npm --prefix sdk run test:consumer` |
| SDK transport recursion | Transport failures do not recursively report themselves as app errors | `npm --prefix sdk run test:unit` |
| Duplicate suppression | The same error object is reported once even if handled capture and runtime auto-capture both see it | `npm --prefix sdk run test:unit` |
| Browser token flow | Browser-key delivery still exchanges a token and posts error telemetry | `npm --prefix sdk run test:unit` |

## Prepublish Checklist

1. Run `npm --prefix sdk run test`.
2. Run `npm --prefix sdk run pack:dry-run`.
3. Run `./.venv/bin/python -m pytest agent-platform/tests/test_sdk_bootstrap_harness.py agent-platform/tests/test_sdk_bootstrap_fallback.py -q`.
4. Verify the automatic browser bootstrap still proposes changes for the connected-repo fixture:
   - `client/src/stimpact.ts`
   - `client/src/lib/queryClient.ts`
   - `client/src/lib/xanoClient.ts`
5. Apply the generated patch to a clean connected-repo-style checkout and run its real build:
   - `npm install`
   - `npm run build`
6. Run one live browser staging drill:
   - confirm `POST /telemetry/browser-token`
   - confirm `POST /telemetry/error`
   - capture the returned `telemetry_id`
   - verify downstream evidence using logs and incident visibility
7. Only publish after the browser drill shows the original app error message, not an SDK integration-layer error.

## Publish Notes

- `sdk/package.json` uses `prepack` to rebuild `dist/` before packing.
- `sdk/package.json` uses `prepublishOnly` to force the SDK test suite before publish.
- The integration generator should depend on the shared browser helper contract, not on repo-specific component code.

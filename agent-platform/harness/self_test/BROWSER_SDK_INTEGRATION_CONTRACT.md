# Browser SDK Integration Contract

Use this contract when changing the browser SDK or the automatic bootstrap generator.

## Package-Level Contract

The published `@stimpact/sdk` package must expose these browser-facing runtime methods on `StimpactClient`:

- `captureError()`
- `captureHandledError()`
- `wrap()`
- `wrapAsync()`
- `registerBrowserAutoCapture()`

The package must also continue to support:

- `browserKey`
- `browserTokenEndpoint`
- `tokenProvider`
- `startHeartbeat()`
- `ping()`

## Generated Helper Contract

The generated browser helper in `stimpact.ts` or `stimpact-provider.tsx` is the only integration surface that app-specific files should depend on.

For Vite and other browser helpers, the generated module should export:

- `installStimpact()`
- `captureHandledError()`
- `wrapStimpact()`
- `wrapStimpactAsync()`
- `getStimpactClient()`
- `pingStimpact()`

The helper owns SDK initialization, heartbeat startup, runtime auto-capture, and any temporary compatibility logic needed during release rollouts.

## Shared Boundary Contract

Shared app boundaries such as `queryClient.ts` and request wrappers should only depend on the generated helper contract, not on the raw SDK instance shape.

Preferred imports:

- `captureHandledError` for handled framework and request-wrapper failures
- `wrapStimpact` or `wrapStimpactAsync` where a shared wrapper is more natural than a manual `try`/`catch`

Avoid:

- reaching into `window.__stimpact`
- calling SDK internals directly from feature components
- duplicating capture logic in both component-level `onError` handlers and shared request/query wrappers unless the events are intentionally distinct

## Verification Expectations

Any browser SDK or bootstrap change should preserve all of the following:

1. Shared request wrappers can capture handled failures and still rethrow for the app UI.
2. React Query query failures can be captured without removing the existing error UI.
3. React Query mutation failures can be captured without removing toast notifications.
4. Uncaught browser errors and unhandled promise rejections still flow through `registerBrowserAutoCapture()`.
5. Duplicate events for the same error object are suppressed.

# Capture-Only Verification

Use this sequence to verify SDK capture coverage before testing incident creation, sandbox reproduction, or autonomous repair.

## Objective

Prove that each supported runtime both detects the target failure class and successfully persists telemetry in Stimpact.

The capture-only pass is successful when:

- the runtime surfaces the failure through the expected capture path
- the SDK attempts delivery with the expected credential path
- telemetry is accepted with a `telemetry_id`, then persisted and queryable in Stimpact
- no incident or autonomous run behavior is required to call the pass successful

## Browser Checks

### 1. Uncaught browser error

- Seed a low-risk uncaught browser failure behind a deliberate UI action.
- Trigger the action once in a deployed environment.
- Confirm the browser runtime uses `registerBrowserAutoCapture()`.
- Confirm the browser receives `202 Accepted` from `POST /telemetry/error` and record the returned `telemetry_id`.
- Verify the telemetry record contains the expected error message, stacktrace, service, environment, and commit SHA.

### 2. Handled browser error

- Seed a failure inside a `try`/`catch`, mutation `onError`, request wrapper, or framework callback.
- Confirm the app calls `captureHandledError()` or a shared wrapper such as `wrapAsync()`.
- Trigger the action once.
- Confirm the browser receives `202 Accepted` from `POST /telemetry/error` and record the returned `telemetry_id`.
- Verify exactly one telemetry record is persisted for that failure path.

## JavaScript Server Checks

### 3. Uncaught process error

- Run the server with `registerProcessAutoCapture()` enabled.
- Trigger an uncaught exception or unhandled rejection in a controlled path.
- Verify the telemetry record is persisted with the server service name and environment.

### 4. Handled server error

- Trigger a handled exception inside a route, job, or service boundary that uses `captureHandledError()`, `wrap()`, or `wrapAsync()`.
- Verify the telemetry record is persisted without waiting for a process crash.

## Python Checks

### 5. Uncaught Python exception

- Run the Python service with `install_auto_capture()` enabled.
- Trigger a controlled uncaught exception in the main request or task lifecycle.
- Verify the telemetry record is persisted with the expected service, environment, and stacktrace.

### 6. Handled Python exception

- Trigger a handled exception in a path instrumented with `capture_handled_exception()`, `wrap()`, or `wrap_async()`.
- Verify the telemetry record is persisted without requiring the process to terminate.

## Verification Rules

- Use one seeded failure at a time while validating a new capture surface.
- Prefer distinctive error messages so telemetry records are easy to attribute.
- Treat heartbeat verification as liveness only; it does not prove a browser error was captured.
- Verify `POST /telemetry/error` returned `202` and note the `telemetry_id` before checking incidents, outbox processing, or autonomous run launch.
- Use the accepted `telemetry_id`, `telemetry_error_accepted` log entry, and downstream incident evidence together when proving end-to-end browser capture.
- If telemetry is missing, debug capture and delivery first; do not treat the failure as an incident-pipeline issue yet.

import type {
  BrowserAutoCaptureOptions,
  BrowserCaptureSubscription,
  StimpactBreadcrumb,
  CaptureErrorInput,
  ErrorCaptureContext,
  HeartbeatInput,
  HeartbeatScheduleOptions,
  HeartbeatSubscription,
  ProcessAutoCaptureOptions,
  ProcessCaptureSubscription,
  ProcessListenerTarget,
  StimpactContexts,
  StimpactClientOptions,
  StimpactEnvironment,
  StimpactTags,
  StimpactUser,
} from "./types.js";

type TelemetryPayload = {
  project_id: string;
  environment: StimpactEnvironment;
  service: string;
  error_message: string;
  stacktrace: string;
  request?: CaptureErrorInput["request"];
  response?: CaptureErrorInput["response"];
  commit_sha?: string | null;
  release?: string | null;
  dist?: string | null;
  user?: StimpactUser | null;
  tags?: StimpactTags;
  contexts?: StimpactContexts;
  breadcrumbs?: StimpactBreadcrumb[];
  session_id?: string | null;
  timestamp: string;
  handled?: boolean | null;
};

type HeartbeatPayload = {
  project_id: string;
  environment: StimpactEnvironment;
  service: string;
  commit_sha?: string | null;
  release?: string | null;
  dist?: string | null;
  session_id?: string | null;
  timestamp: string;
};

type NormalizedError = {
  message: string;
  stacktrace: string;
};

type BrowserTokenResponse = {
  token?: string;
  expires_at?: string;
  expires_in_seconds?: number;
};

const DEFAULT_REDACTED_HEADERS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "proxy-authorization",
  "x-api-key",
  "x-stimpact-project-key",
]);
const DEFAULT_BREADCRUMB_LIMIT = 100;
const DEFAULT_SESSION_IDLE_TIMEOUT_MS = 30 * 60_000;
const DEFAULT_OFFLINE_QUEUE_LIMIT = 25;
const CAPTURE_IN_FLIGHT = Symbol("stimpact.captureInFlight");
const CAPTURE_REPORTED = Symbol("stimpact.captureReported");

export class StimpactRequestError extends Error {
  status: number | null;
  retryable: boolean;
  responseBody: string | null;

  constructor(message: string, options: { status?: number | null; retryable?: boolean; responseBody?: string | null } = {}) {
    super(message);
    this.name = "StimpactRequestError";
    this.status = options.status ?? null;
    this.retryable = options.retryable ?? false;
    this.responseBody = options.responseBody ?? null;
  }
}

export class StimpactClient {
  private readonly options: Required<
    Pick<
      StimpactClientOptions,
      | "baseUrl"
      | "projectId"
      | "service"
      | "timeoutMs"
      | "retryAttempts"
      | "retryDelayMs"
      | "browserTokenFailureCooldownMs"
      | "captureRequestContext"
      | "captureResponseContext"
      | "includeBodies"
      | "redactedHeaders"
      | "maxValueLength"
      | "breadcrumbLimit"
    >
  > &
    Pick<
      StimpactClientOptions,
      | "apiKey"
      | "browserKey"
      | "browserTokenEndpoint"
      | "tokenProvider"
      | "environment"
      | "release"
      | "dist"
      | "fetchImpl"
      | "headers"
    >;
  private cachedBrowserToken: string | null = null;
  private cachedBrowserTokenExpiresAtMs = 0;
  private browserTokenPromise: Promise<string> | null = null;
  private browserTokenFailure: StimpactRequestError | null = null;
  private browserTokenFailureBlockedUntilMs = 0;
  private readonly inFlightErrors = new WeakSet<object>();
  private readonly reportedErrors = new WeakSet<object>();
  private user: StimpactUser | null = null;
  private readonly tags = new Map<string, string>();
  private readonly contexts = new Map<string, Record<string, unknown>>();
  private breadcrumbs: StimpactBreadcrumb[] = [];
  private sessionId: string | null = null;
  private lastActivityAtMs = 0;
  private browserActivityBound = false;
  private offlineQueue: TelemetryPayload[] = [];
  private offlineFlushBound = false;

  constructor(options: StimpactClientOptions) {
    if (!options.apiKey && !options.browserKey && !options.browserTokenEndpoint && !options.tokenProvider) {
      throw new Error(
        "StimpactClient requires apiKey, browserKey, browserTokenEndpoint, or tokenProvider.",
      );
    }
    this.options = {
      ...options,
      baseUrl: options.baseUrl.replace(/\/$/, ""),
      environment: options.environment ?? "production",
      fetchImpl: options.fetchImpl ?? fetch,
      headers: options.headers ?? {},
      timeoutMs: options.timeoutMs ?? 5_000,
      retryAttempts: options.retryAttempts ?? 2,
      retryDelayMs: options.retryDelayMs ?? 250,
      browserTokenFailureCooldownMs: options.browserTokenFailureCooldownMs ?? 60_000,
      captureRequestContext: options.captureRequestContext ?? false,
      captureResponseContext: options.captureResponseContext ?? false,
      includeBodies: options.includeBodies ?? false,
      redactedHeaders: options.redactedHeaders ?? [],
      maxValueLength: options.maxValueLength ?? 2_048,
      breadcrumbLimit: options.breadcrumbLimit ?? DEFAULT_BREADCRUMB_LIMIT,
    };
    this.touchSession();
  }

  async captureError(input: CaptureErrorInput): Promise<void> {
    await this.captureWithState({ ...input, handled: input.handled ?? false });
  }

  async captureHandledError(input: CaptureErrorInput): Promise<void> {
    await this.captureWithState({ ...input, handled: input.handled ?? true });
  }

  /**
   * Report an expected error (e.g. a validation failure or a login with the
   * wrong password) explicitly tagged as handled, so the platform does not
   * kick off an autonomous repair run for it.
   */
  async captureHandled(input: CaptureErrorInput): Promise<void> {
    await this.captureHandledError(input);
  }

  setUser(user: StimpactUser | null): void {
    this.user = user ? sanitizeUser(user, this.options.maxValueLength) ?? null : null;
  }

  clearUser(): void {
    this.user = null;
  }

  setTags(tags: StimpactTags): void {
    for (const [key, value] of Object.entries(tags)) {
      if (!key) {
        continue;
      }
      this.tags.set(clampString(key, 128), clampString(String(value), 256));
    }
  }

  setContext(name: string, value: Record<string, unknown>): void {
    if (!name) {
      return;
    }
    this.contexts.set(
      clampString(name, 128),
      sanitizeUnknown(value, this.options) as Record<string, unknown>,
    );
  }

  clearContext(name: string): void {
    this.contexts.delete(name);
  }

  addBreadcrumb(input: Omit<StimpactBreadcrumb, "ts"> & { ts?: string | Date }): void {
    const breadcrumb = normalizeBreadcrumb(input, this.options.maxValueLength);
    if (!breadcrumb) {
      return;
    }
    this.touchSession();
    this.breadcrumbs = [...this.breadcrumbs, breadcrumb].slice(-this.options.breadcrumbLimit);
  }

  clearBreadcrumbs(): void {
    this.breadcrumbs = [];
  }

  async sendHeartbeat(input: HeartbeatInput = {}): Promise<void> {
    const payload: HeartbeatPayload = {
      project_id: this.options.projectId,
      environment: input.environment ?? this.options.environment ?? "production",
      service: input.service ?? this.options.service,
      commit_sha: input.commitSha ?? null,
      release: input.release ?? this.options.release ?? null,
      dist: input.dist ?? this.options.dist ?? null,
      session_id: input.sessionId ?? this.getSessionId(),
      timestamp: normalizeTimestamp(input.timestamp),
    };
    await this.sendHeartbeatPayload(payload);
  }

  async ping(input: HeartbeatInput = {}): Promise<void> {
    await this.sendHeartbeat(input);
  }

  wrap<T>(
    operation: () => T,
    context?: ErrorCaptureContext,
  ): T {
    try {
      return operation();
    } catch (error) {
      this.captureSyncFailure(error, context);
      throw error;
    }
  }

  async wrapAsync<T>(
    operation: () => Promise<T>,
    context?: ErrorCaptureContext,
  ): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      try {
        await this.captureHandledError({
          ...context,
          error,
        });
      } catch (captureFailure) {
        this.attachCaptureFailure(error, captureFailure);
      }
      throw error;
    }
  }

  registerProcessAutoCapture(
    options: ProcessAutoCaptureOptions = {},
  ): ProcessCaptureSubscription {
    const processTarget = options.processTarget ?? resolveProcessTarget();
    if (!processTarget) {
      return { dispose: () => undefined };
    }

    const captureUncaughtExceptions = options.captureUncaughtExceptions ?? true;
    const captureUnhandledRejections =
      options.captureUnhandledRejections ?? true;

    const uncaughtExceptionListener = (error: unknown) => {
      if (this.shouldIgnoreAutoCapturedError(error)) {
        return;
      }
      void this.captureError({
        error: toError(error),
        service: this.options.service,
        handled: false,
      }).catch(() => undefined);
    };

    const unhandledRejectionListener = (reason: unknown) => {
      if (this.shouldIgnoreAutoCapturedError(reason)) {
        return;
      }
      void this.captureError({
        error: toError(reason),
        service: this.options.service,
        handled: false,
      }).catch(() => undefined);
    };

    if (captureUncaughtExceptions) {
      addProcessListener(processTarget, "uncaughtException", uncaughtExceptionListener);
    }
    if (captureUnhandledRejections) {
      addProcessListener(processTarget, "unhandledRejection", unhandledRejectionListener);
    }

    return {
      dispose: () => {
        if (captureUncaughtExceptions) {
          removeProcessListener(processTarget, "uncaughtException", uncaughtExceptionListener);
        }
        if (captureUnhandledRejections) {
          removeProcessListener(processTarget, "unhandledRejection", unhandledRejectionListener);
        }
      },
    };
  }

  private async captureWithState(input: CaptureErrorInput): Promise<void> {
    this.touchSession();
    const trackedError = asTrackableObject(input.error);
    if (trackedError && (this.inFlightErrors.has(trackedError) || this.reportedErrors.has(trackedError))) {
      return;
    }
    if (trackedError) {
      this.inFlightErrors.add(trackedError);
      markCaptureState(trackedError, CAPTURE_IN_FLIGHT);
    }

    const normalized = normalizeError(input.error, this.options.maxValueLength);
    const payload: TelemetryPayload = {
      project_id: this.options.projectId,
      environment: input.environment ?? this.options.environment ?? "production",
      service: input.service ?? this.options.service,
      error_message: normalized.message,
      stacktrace: normalized.stacktrace,
      request: this.options.captureRequestContext
        ? sanitizeRequestContext(input.request, this.options)
        : undefined,
      response: this.options.captureResponseContext
        ? sanitizeResponseContext(input.response, this.options)
        : undefined,
      commit_sha: input.commitSha ?? null,
      release: input.release ?? this.options.release ?? null,
      dist: input.dist ?? this.options.dist ?? null,
      user: input.user === undefined ? this.user : sanitizeUser(input.user, this.options.maxValueLength),
      tags: mergeTags(this.tags, input.tags),
      contexts: mergeContexts(this.contexts, input.contexts, this.options),
      breadcrumbs: mergeBreadcrumbs(this.breadcrumbs, input.breadcrumbs, this.options.maxValueLength),
      session_id: input.sessionId ?? this.getSessionId(),
      timestamp: normalizeTimestamp(input.timestamp),
      handled: typeof input.handled === "boolean" ? input.handled : undefined,
    };

    try {
      await this.sendTelemetry(payload);
      if (trackedError) {
        this.reportedErrors.add(trackedError);
        markCaptureState(trackedError, CAPTURE_REPORTED);
      }
    } catch (error) {
      if (trackedError) {
        clearCaptureState(trackedError, CAPTURE_REPORTED);
      }
      throw error;
    } finally {
      if (trackedError) {
        this.inFlightErrors.delete(trackedError);
        clearCaptureState(trackedError, CAPTURE_IN_FLIGHT);
      }
    }
  }

  startHeartbeat(options: HeartbeatScheduleOptions = {}): HeartbeatSubscription {
    const intervalMs = options.intervalMs ?? 300_000;
    const jitterRatio = clampNumber(options.jitterRatio ?? 0.1, 0, 0.5);
    const immediate = options.immediate ?? true;
    const pauseWhenHidden = options.pauseWhenHidden ?? false;
    const skipWhenOffline = options.skipWhenOffline ?? true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;
    let paused = false;

    const clearScheduledHeartbeat = () => {
      if (timeoutId !== null && typeof clearTimeout !== "undefined") {
        clearTimeout(timeoutId);
      }
      timeoutId = null;
    };

    const isDocumentHidden = () =>
      typeof document !== "undefined" && document.visibilityState === "hidden";
    const isNavigatorOffline = () =>
      typeof navigator !== "undefined" &&
      "onLine" in navigator &&
      navigator.onLine === false;

    const shouldSkipHeartbeat = () =>
      (pauseWhenHidden && isDocumentHidden()) || (skipWhenOffline && isNavigatorOffline());

    const scheduleNextHeartbeat = () => {
      if (disposed || paused || typeof setTimeout === "undefined") {
        return;
      }
      clearScheduledHeartbeat();
      const jitterWindowMs = Math.round(intervalMs * jitterRatio);
      const delayMs =
        jitterWindowMs > 0 ? intervalMs - jitterWindowMs + Math.round(Math.random() * jitterWindowMs * 2) : intervalMs;
      timeoutId = setTimeout(() => {
        void triggerHeartbeat().catch(() => undefined);
      }, delayMs);
    };

    const triggerHeartbeat = async (input: HeartbeatInput = options) => {
      if (disposed) {
        return;
      }
      if (shouldSkipHeartbeat()) {
        scheduleNextHeartbeat();
        return;
      }
      try {
        await this.sendHeartbeat(input);
      } finally {
        scheduleNextHeartbeat();
      }
    };

    const resume = () => {
      if (disposed) {
        return;
      }
      paused = false;
      scheduleNextHeartbeat();
    };

    const pause = () => {
      paused = true;
      clearScheduledHeartbeat();
    };

    const handleVisibilityChange = () => {
      if (!pauseWhenHidden || disposed) {
        return;
      }
      if (isDocumentHidden()) {
        pause();
        return;
      }
      resume();
    };

    const handleOnline = () => {
      if (!skipWhenOffline || disposed) {
        return;
      }
      resume();
      void triggerHeartbeat().catch(() => undefined);
    };

    const handleOffline = () => {
      if (!skipWhenOffline || disposed) {
        return;
      }
      pause();
    };

    if (pauseWhenHidden && typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }
    if (skipWhenOffline && typeof window !== "undefined") {
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
    }

    if (immediate) {
      void triggerHeartbeat().catch(() => undefined);
    } else {
      scheduleNextHeartbeat();
    }

    return {
      dispose: () => {
        disposed = true;
        clearScheduledHeartbeat();
        if (pauseWhenHidden && typeof document !== "undefined") {
          document.removeEventListener("visibilitychange", handleVisibilityChange);
        }
        if (skipWhenOffline && typeof window !== "undefined") {
          window.removeEventListener("online", handleOnline);
          window.removeEventListener("offline", handleOffline);
        }
      },
      pause,
      resume,
      triggerNow: (input: HeartbeatInput = options) => triggerHeartbeat(input),
      isRunning: () => !disposed && !paused,
    };
  }

  registerBrowserAutoCapture(
    options: BrowserAutoCaptureOptions = {},
  ): BrowserCaptureSubscription {
    if (typeof window === "undefined") {
      return { dispose: () => undefined };
    }
    this.ensureBrowserRuntimeObservers();

    const captureWindowErrors = options.captureWindowErrors ?? true;
    const captureUnhandledRejections =
      options.captureUnhandledRejections ?? true;

    const errorListener = (event: ErrorEvent) => {
      if (this.shouldIgnoreAutoCapturedError(event.error)) {
        return;
      }
      void this.captureError({
        error: event.error ?? event.message,
        service: this.options.service,
        handled: false,
      }).catch(() => undefined);
    };

    const rejectionListener = (event: PromiseRejectionEvent) => {
      if (this.shouldIgnoreAutoCapturedError(event.reason)) {
        return;
      }
      void this.captureError({
        error: event.reason ?? "Unhandled promise rejection",
        service: this.options.service,
        handled: false,
      }).catch(() => undefined);
    };

    if (captureWindowErrors) {
      window.addEventListener("error", errorListener);
    }
    if (captureUnhandledRejections) {
      window.addEventListener("unhandledrejection", rejectionListener);
    }

    return {
      dispose: () => {
        if (captureWindowErrors) {
          window.removeEventListener("error", errorListener);
        }
        if (captureUnhandledRejections) {
          window.removeEventListener("unhandledrejection", rejectionListener);
        }
      },
    };
  }

  private ensureBrowserRuntimeObservers(): void {
    this.ensureSession();
    this.ensureOfflineFlushListener();
    if (this.browserActivityBound || typeof window === "undefined") {
      return;
    }
    this.browserActivityBound = true;
    const recordVisibility = () => {
      this.touchSession();
      this.addBreadcrumb({
        category: "navigation.visibility",
        message: typeof document !== "undefined" ? document.visibilityState : "unknown",
        level: "info",
      });
    };
    window.addEventListener("online", () => {
      this.touchSession();
      void this.flushOfflineQueue().catch(() => undefined);
    });
    window.addEventListener("pagehide", () => {
      this.touchSession();
    });
    window.addEventListener("click", (event) => {
      this.touchSession();
      this.addBreadcrumb({
        category: "ui.click",
        message: describeEventTarget(event.target),
        level: "info",
      });
    });
    window.addEventListener("keydown", (event) => {
      this.touchSession();
      this.addBreadcrumb({
        category: "ui.keydown",
        message: `key:${event.key}`,
        level: "debug",
      });
    });
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", recordVisibility);
    }
    this.instrumentHistoryBreadcrumbs();
    this.instrumentNetworkBreadcrumbs();
    this.instrumentConsoleBreadcrumbs();
  }

  private instrumentHistoryBreadcrumbs(): void {
    if (
      typeof window === "undefined" ||
      !window.history ||
      typeof window.history.pushState !== "function" ||
      typeof window.history.replaceState !== "function" ||
      hasGlobalFlag("__stimpactHistoryWrapped")
    ) {
      return;
    }
    setGlobalFlag("__stimpactHistoryWrapped");
    const originalPushState = window.history.pushState.bind(window.history);
    const originalReplaceState = window.history.replaceState.bind(window.history);
    window.history.pushState = ((...args: Parameters<History["pushState"]>) => {
      const result = originalPushState(...args);
      this.touchSession();
      this.addBreadcrumb({
        category: "navigation.pushState",
        message: String(args[2] ?? window.location.pathname),
        level: "info",
      });
      return result;
    }) as History["pushState"];
    window.history.replaceState = ((...args: Parameters<History["replaceState"]>) => {
      const result = originalReplaceState(...args);
      this.touchSession();
      this.addBreadcrumb({
        category: "navigation.replaceState",
        message: String(args[2] ?? window.location.pathname),
        level: "debug",
      });
      return result;
    }) as History["replaceState"];
    window.addEventListener("popstate", () => {
      this.touchSession();
      this.addBreadcrumb({
        category: "navigation.popstate",
        message: window.location.pathname,
        level: "info",
      });
    });
  }

  private instrumentConsoleBreadcrumbs(): void {
    if (typeof console === "undefined" || hasGlobalFlag("__stimpactConsoleWrapped")) {
      return;
    }
    setGlobalFlag("__stimpactConsoleWrapped");
    const originalError = console.error.bind(console);
    const originalWarn = console.warn.bind(console);
    console.error = (...args: unknown[]) => {
      this.addBreadcrumb({
        category: "console.error",
        message: summarizeConsoleArgs(args, this.options.maxValueLength),
        level: "error",
      });
      originalError(...args);
    };
    console.warn = (...args: unknown[]) => {
      this.addBreadcrumb({
        category: "console.warn",
        message: summarizeConsoleArgs(args, this.options.maxValueLength),
        level: "warning",
      });
      originalWarn(...args);
    };
  }

  private instrumentNetworkBreadcrumbs(): void {
    if (typeof globalThis.fetch === "function" && !hasGlobalFlag("__stimpactFetchWrapped")) {
      setGlobalFlag("__stimpactFetchWrapped");
      const originalFetch = globalThis.fetch.bind(globalThis);
      globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        const startedAt = Date.now();
        const method = init?.method ?? "GET";
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        try {
          const response = await originalFetch(input, init);
          this.addBreadcrumb({
            category: "fetch",
            message: `${method} ${url}`,
            level: response.ok ? "info" : "warning",
            data: {
              status: response.status,
              duration_ms: Date.now() - startedAt,
            },
          });
          return response;
        } catch (error) {
          this.addBreadcrumb({
            category: "fetch",
            message: `${method} ${url}`,
            level: "error",
            data: {
              duration_ms: Date.now() - startedAt,
              error: error instanceof Error ? error.message : String(error),
            },
          });
          throw error;
        }
      }) as typeof fetch;
    }
    if (typeof XMLHttpRequest === "undefined" || hasGlobalFlag("__stimpactXhrWrapped")) {
      return;
    }
    setGlobalFlag("__stimpactXhrWrapped");
    const client = this;
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (
      method: string,
      url: string | URL,
      async?: boolean,
      username?: string | null,
      password?: string | null,
    ) {
      (this as XMLHttpRequest & { __stimpactMethod?: string; __stimpactUrl?: string }).__stimpactMethod = method;
      (this as XMLHttpRequest & { __stimpactMethod?: string; __stimpactUrl?: string }).__stimpactUrl = String(url);
      return originalOpen.call(this, method, url, async ?? true, username ?? undefined, password ?? undefined);
    };
    XMLHttpRequest.prototype.send = function (...args) {
      const startedAt = Date.now();
      this.addEventListener("loadend", () => {
        const xhr = this as XMLHttpRequest & { __stimpactMethod?: string; __stimpactUrl?: string };
        const method = xhr.__stimpactMethod ?? "GET";
        const url = xhr.__stimpactUrl ?? "";
        client.addBreadcrumb({
          category: "xhr",
          message: `${method} ${url}`,
          level: xhr.status >= 400 ? "warning" : "info",
          data: {
            status: xhr.status,
            duration_ms: Date.now() - startedAt,
          },
        });
      }, { once: true });
      return originalSend.apply(this, args);
    };
  }

  private getSessionId(): string | null {
    return this.ensureSession();
  }

  private ensureSession(): string | null {
    if (typeof window === "undefined") {
      return null;
    }
    const now = Date.now();
    if (!this.sessionId || now - this.lastActivityAtMs > DEFAULT_SESSION_IDLE_TIMEOUT_MS) {
      this.sessionId = createSessionId();
    }
    this.lastActivityAtMs = now;
    return this.sessionId;
  }

  private touchSession(): void {
    this.ensureSession();
  }

  private isBrowserOffline(): boolean {
    return (
      typeof navigator !== "undefined" &&
      "onLine" in navigator &&
      navigator.onLine === false
    );
  }

  private shouldUseKeepalive(payload: TelemetryPayload | HeartbeatPayload): boolean {
    return "error_message" in payload && typeof document !== "undefined" && document.visibilityState === "hidden";
  }

  private enqueueOfflinePayload(payload: TelemetryPayload): void {
    this.offlineQueue = [...this.offlineQueue, payload].slice(-DEFAULT_OFFLINE_QUEUE_LIMIT);
  }

  private ensureOfflineFlushListener(): void {
    if (this.offlineFlushBound || typeof window === "undefined") {
      return;
    }
    this.offlineFlushBound = true;
    window.addEventListener("online", () => {
      void this.flushOfflineQueue().catch(() => undefined);
    });
  }

  private async flushOfflineQueue(): Promise<void> {
    if (this.offlineQueue.length === 0 || this.isBrowserOffline()) {
      return;
    }
    const queued = [...this.offlineQueue];
    this.offlineQueue = [];
    for (const payload of queued) {
      await this.sendTelemetry(payload);
    }
  }

  private shouldIgnoreAutoCapturedError(error: unknown): boolean {
    if (error instanceof StimpactRequestError) {
      return true;
    }
    const trackedError = asTrackableObject(error);
    if (!trackedError) {
      return false;
    }
    return (
      this.inFlightErrors.has(trackedError) ||
      this.reportedErrors.has(trackedError) ||
      hasCaptureState(trackedError, CAPTURE_IN_FLIGHT) ||
      hasCaptureState(trackedError, CAPTURE_REPORTED)
    );
  }

  private captureSyncFailure(
    error: unknown,
    context?: ErrorCaptureContext,
  ): void {
    void this.captureHandledError({
      ...context,
      error,
    }).catch((captureFailure) => {
      this.attachCaptureFailure(error, captureFailure);
    });
  }

  private attachCaptureFailure(error: unknown, captureFailure: unknown): void {
    if (error instanceof Error) {
      Object.defineProperty(error, "captureFailure", {
        value: captureFailure,
        configurable: true,
      });
    }
  }

  private async sendTelemetry(payload: TelemetryPayload): Promise<void> {
    if (this.isBrowserOffline()) {
      this.enqueueOfflinePayload(payload);
      this.ensureOfflineFlushListener();
      return;
    }
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.options.retryAttempts; attempt += 1) {
      try {
        await this.sendTelemetryOnce(payload);
        return;
      } catch (error) {
        lastError = error;
        if (!(error instanceof StimpactRequestError) || !error.retryable || attempt === this.options.retryAttempts) {
          throw error;
        }
        await delay(this.options.retryDelayMs * (attempt + 1));
      }
    }

    throw lastError instanceof Error
      ? lastError
      : new StimpactRequestError("Telemetry delivery failed.");
  }

  private async sendHeartbeatPayload(payload: HeartbeatPayload): Promise<void> {
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.options.retryAttempts; attempt += 1) {
      try {
        await this.sendJson(`${this.options.baseUrl}/telemetry/heartbeat`, payload);
        return;
      } catch (error) {
        lastError = error;
        if (!(error instanceof StimpactRequestError) || !error.retryable || attempt === this.options.retryAttempts) {
          throw error;
        }
        await delay(this.options.retryDelayMs * (attempt + 1));
      }
    }

    throw lastError instanceof Error
      ? lastError
      : new StimpactRequestError("Telemetry heartbeat delivery failed.");
  }

  private async sendTelemetryOnce(payload: TelemetryPayload): Promise<void> {
    await this.sendJson(`${this.options.baseUrl}/telemetry/error`, payload);
  }

  private async sendJson(url: string, payload: TelemetryPayload | HeartbeatPayload): Promise<void> {
    const fetchImpl = this.options.fetchImpl ?? fetch;
    const controller =
      typeof AbortController === "undefined" ? null : new AbortController();
    const timeout = controller
      ? setTimeout(() => controller.abort(), this.options.timeoutMs)
      : null;

    try {
      const authHeaders = await this.buildAuthHeaders(payload);
      const response = await fetchImpl(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
          ...this.options.headers,
        },
        body: JSON.stringify(payload),
        keepalive: this.shouldUseKeepalive(payload),
        signal: controller?.signal,
      });

      if (!response.ok) {
        const responseBody = await safeReadResponseText(response);
        throw new StimpactRequestError(
          `Telemetry delivery failed with status ${response.status}.`,
          {
            status: response.status,
            retryable: response.status >= 500 || response.status === 429,
            responseBody,
          },
        );
      }
    } catch (error) {
      if (error instanceof StimpactRequestError) {
        throw error;
      }
      throw new StimpactRequestError("Telemetry delivery failed before the platform acknowledged it.", {
        retryable: true,
      });
    } finally {
      if (timeout !== null) {
        clearTimeout(timeout);
      }
    }
  }

  private async buildAuthHeaders(
    payload: TelemetryPayload | HeartbeatPayload,
  ): Promise<Record<string, string>> {
    if (this.options.apiKey) {
      return {
        "X-Stimpact-Project-Key": this.options.apiKey,
      };
    }
    const token = await this.getBrowserToken(payload);
    return {
      Authorization: `Bearer ${token}`,
    };
  }

  private async getBrowserToken(
    payload: TelemetryPayload | HeartbeatPayload,
  ): Promise<string> {
    if (this.options.tokenProvider) {
      return this.options.tokenProvider();
    }
    const refreshThresholdMs = 15_000;
    if (
      this.cachedBrowserToken &&
      Date.now() + refreshThresholdMs < this.cachedBrowserTokenExpiresAtMs
    ) {
      return this.cachedBrowserToken;
    }
    if (
      this.browserTokenFailure &&
      Date.now() < this.browserTokenFailureBlockedUntilMs
    ) {
      throw this.browserTokenFailure;
    }
    if (this.browserTokenPromise) {
      return this.browserTokenPromise;
    }
    this.browserTokenPromise = this.fetchBrowserToken(payload).finally(() => {
      this.browserTokenPromise = null;
    });
    return this.browserTokenPromise;
  }

  private async fetchBrowserToken(
    payload: TelemetryPayload | HeartbeatPayload,
  ): Promise<string> {
    const endpoint =
      this.options.browserTokenEndpoint ??
      `${this.options.baseUrl}/telemetry/browser-token`;
    const body = {
      project_id: this.options.projectId,
      browser_key: this.options.browserKey,
      service: payload.service,
      environment: payload.environment,
    };
    try {
      const response = await this.performJsonRequest(endpoint, body);
      const parsed = (await safeReadResponseJson(response)) as BrowserTokenResponse | null;
      const token = typeof parsed?.token === "string" ? parsed.token : null;
      if (!token) {
        throw new StimpactRequestError(
          "Browser token request succeeded without a token payload.",
        );
      }
      const expiresAtMs = resolveTokenExpiryMs(parsed);
      this.cachedBrowserToken = token;
      this.cachedBrowserTokenExpiresAtMs = expiresAtMs;
      this.browserTokenFailure = null;
      this.browserTokenFailureBlockedUntilMs = 0;
      return token;
    } catch (error) {
      if (error instanceof StimpactRequestError) {
        this.rememberBrowserTokenFailure(error);
      }
      throw error;
    }
  }

  private async performJsonRequest(
    url: string,
    payload: Record<string, unknown>,
  ): Promise<Response> {
    const fetchImpl = this.options.fetchImpl ?? fetch;
    const controller =
      typeof AbortController === "undefined" ? null : new AbortController();
    const timeout = controller
      ? setTimeout(() => controller.abort(), this.options.timeoutMs)
      : null;
    try {
      const response = await fetchImpl(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...this.options.headers,
        },
        body: JSON.stringify(payload),
        signal: controller?.signal,
      });
      if (!response.ok) {
        const responseBody = await safeReadResponseText(response);
        throw new StimpactRequestError(
          `Request failed with status ${response.status}.`,
          {
            status: response.status,
            retryable: response.status >= 500 || response.status === 429,
            responseBody,
          },
        );
      }
      return response;
    } catch (error) {
      if (error instanceof StimpactRequestError) {
        throw error;
      }
      throw new StimpactRequestError(
        "Request failed before the platform acknowledged it.",
        {
          retryable: true,
        },
      );
    } finally {
      if (timeout !== null) {
        clearTimeout(timeout);
      }
    }
  }

  private rememberBrowserTokenFailure(error: StimpactRequestError): void {
    if (error.retryable) {
      return;
    }
    this.cachedBrowserToken = null;
    this.cachedBrowserTokenExpiresAtMs = 0;
    this.browserTokenFailure = error;
    this.browserTokenFailureBlockedUntilMs =
      Date.now() + this.options.browserTokenFailureCooldownMs;
  }
}

function sanitizeUser(
  user: StimpactUser | null | undefined,
  maxValueLength: number,
): StimpactUser | null | undefined {
  if (user === undefined) {
    return undefined;
  }
  if (user === null) {
    return null;
  }
  return omitUndefined({
    id: user.id ? clampString(user.id, maxValueLength) : undefined,
    email: user.email ? clampString(user.email, maxValueLength) : undefined,
    username: user.username ? clampString(user.username, maxValueLength) : undefined,
    segment: user.segment ? clampString(user.segment, maxValueLength) : undefined,
  }) ?? null;
}

function mergeTags(
  existing: Map<string, string>,
  tags: StimpactTags | undefined,
): StimpactTags | undefined {
  const merged = new Map(existing);
  for (const [key, value] of Object.entries(tags ?? {})) {
    merged.set(clampString(key, 128), clampString(String(value), 256));
  }
  return merged.size > 0 ? Object.fromEntries(merged) : undefined;
}

function mergeContexts(
  existing: Map<string, Record<string, unknown>>,
  contexts: StimpactContexts | undefined,
  options: Pick<StimpactClientOptions, "includeBodies" | "redactedHeaders" | "maxValueLength">,
): StimpactContexts | undefined {
  const merged = new Map(existing);
  for (const [key, value] of Object.entries(contexts ?? {})) {
    merged.set(
      clampString(key, 128),
      sanitizeUnknown(value, options) as Record<string, unknown>,
    );
  }
  return merged.size > 0 ? Object.fromEntries(merged) : undefined;
}

function mergeBreadcrumbs(
  existing: StimpactBreadcrumb[],
  input: StimpactBreadcrumb[] | undefined,
  maxValueLength: number,
): StimpactBreadcrumb[] | undefined {
  const normalized = [...existing];
  for (const breadcrumb of input ?? []) {
    const normalizedBreadcrumb = normalizeBreadcrumb(breadcrumb, maxValueLength);
    if (normalizedBreadcrumb) {
      normalized.push(normalizedBreadcrumb);
    }
  }
  return normalized.length > 0 ? normalized.slice(-DEFAULT_BREADCRUMB_LIMIT) : undefined;
}

function normalizeBreadcrumb(
  input: Omit<StimpactBreadcrumb, "ts"> & { ts?: string | Date },
  maxValueLength: number,
): StimpactBreadcrumb | null {
  if (!input.category || !input.message) {
    return null;
  }
  return omitUndefined({
    ts: normalizeTimestamp(input.ts),
    category: clampString(input.category, 128),
    message: clampString(input.message, maxValueLength),
    level: input.level,
    data: input.data
      ? (sanitizeUnknown(input.data, {
          includeBodies: false,
          redactedHeaders: [],
          maxValueLength,
        }) as Record<string, unknown>)
      : undefined,
  }) as StimpactBreadcrumb;
}

function describeEventTarget(target: EventTarget | null): string {
  if (!target || typeof Element === "undefined" || !(target instanceof Element)) {
    return "unknown";
  }
  const id = target.id ? `#${target.id}` : "";
  const className =
    typeof target.className === "string" && target.className.trim()
      ? `.${target.className.trim().split(/\s+/).slice(0, 2).join(".")}`
      : "";
  return `${target.tagName.toLowerCase()}${id}${className}`;
}

function summarizeConsoleArgs(args: unknown[], maxValueLength: number): string {
  return clampString(
    args
      .slice(0, 4)
      .map((arg) => (typeof arg === "string" ? arg : safeSerialize(arg)))
      .join(" "),
    maxValueLength,
  );
}

function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `stimpact_${Math.random().toString(36).slice(2, 10)}_${Date.now().toString(36)}`;
}

function hasGlobalFlag(name: string): boolean {
  return Boolean((globalThis as Record<string, unknown>)[name]);
}

function setGlobalFlag(name: string): void {
  (globalThis as Record<string, unknown>)[name] = true;
}

function normalizeTimestamp(value: string | Date | undefined): string {
  if (!value) {
    return new Date().toISOString();
  }
  return value instanceof Date ? value.toISOString() : value;
}

function asTrackableObject(value: unknown): object | null {
  if ((typeof value === "object" && value !== null) || typeof value === "function") {
    return value as object;
  }
  return null;
}

function hasCaptureState(target: object, symbol: symbol): boolean {
  return Boolean((target as Record<PropertyKey, unknown>)[symbol]);
}

function markCaptureState(target: object, symbol: symbol): void {
  Object.defineProperty(target, symbol, {
    value: true,
    configurable: true,
  });
}

function clearCaptureState(target: object, symbol: symbol): void {
  delete (target as Record<PropertyKey, unknown>)[symbol];
}

function toError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }
  return new Error(typeof error === "string" ? error : safeSerialize(error));
}

function resolveProcessTarget(): ProcessListenerTarget | null {
  const candidate = (globalThis as { process?: ProcessListenerTarget }).process;
  return candidate ?? null;
}

function addProcessListener(
  target: ProcessListenerTarget,
  event: string,
  listener: (...args: unknown[]) => void,
): void {
  if (typeof target.on === "function") {
    target.on(event, listener);
    return;
  }
  if (typeof target.addListener === "function") {
    target.addListener(event, listener);
  }
}

function removeProcessListener(
  target: ProcessListenerTarget,
  event: string,
  listener: (...args: unknown[]) => void,
): void {
  if (typeof target.off === "function") {
    target.off(event, listener);
    return;
  }
  if (typeof target.removeListener === "function") {
    target.removeListener(event, listener);
  }
}

function normalizeError(error: unknown, maxValueLength: number): NormalizedError {
  if (error instanceof Error) {
    return {
      message: clampString(error.message || error.name || "Unknown error", maxValueLength),
      stacktrace: clampString(
        error.stack || error.message || error.name,
        maxValueLength * 4,
      ),
    };
  }
  if (typeof error === "string") {
    return {
      message: clampString(error, maxValueLength),
      stacktrace: clampString(error, maxValueLength * 4),
    };
  }
  const sanitized = sanitizeUnknown(error, {
    includeBodies: false,
    maxValueLength,
    redactedHeaders: [],
  });
  const serialized = safeSerialize(sanitized);
  return {
    message:
      typeof sanitized === "object" &&
      sanitized !== null &&
      "message" in sanitized &&
      typeof sanitized.message === "string"
        ? clampString(sanitized.message, maxValueLength)
        : "Unknown error",
    stacktrace: clampString(serialized, maxValueLength * 4),
  };
}

async function safeReadResponseText(response: Response): Promise<string | null> {
  try {
    const text = await response.text();
    return text || null;
  } catch {
    return null;
  }
}

async function safeReadResponseJson(response: Response): Promise<unknown | null> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function sanitizeRequestContext(
  request: CaptureErrorInput["request"],
  options: Pick<
    StimpactClientOptions,
    "includeBodies" | "redactedHeaders" | "maxValueLength"
  >,
): CaptureErrorInput["request"] | undefined {
  if (!request) {
    return undefined;
  }
  return omitUndefined({
    method: request.method
      ? clampString(request.method, 32)
      : undefined,
    url: request.url
      ? clampString(request.url, options.maxValueLength ?? 2_048)
      : undefined,
    headers: sanitizeHeaders(request.headers, options.redactedHeaders, options.maxValueLength),
    body: options.includeBodies
      ? sanitizeUnknown(request.body, options)
      : undefined,
  });
}

function sanitizeResponseContext(
  response: CaptureErrorInput["response"],
  options: Pick<
    StimpactClientOptions,
    "includeBodies" | "redactedHeaders" | "maxValueLength"
  >,
): CaptureErrorInput["response"] | undefined {
  if (!response) {
    return undefined;
  }
  return omitUndefined({
    status_code: response.status_code,
    headers: sanitizeHeaders(response.headers, options.redactedHeaders, options.maxValueLength),
    body: options.includeBodies
      ? sanitizeUnknown(response.body, options)
      : undefined,
  });
}

function sanitizeHeaders(
  headers: Record<string, string> | undefined,
  redactedHeaders: string[] | undefined,
  maxValueLength = 2_048,
): Record<string, string> | undefined {
  if (!headers) {
    return undefined;
  }
  const extraRedactions = new Set(
    (redactedHeaders ?? []).map((value) => value.toLowerCase()),
  );
  const entries = Object.entries(headers)
    .slice(0, 40)
    .map(([key, value]) => {
      const lowerKey = key.toLowerCase();
      const shouldRedact =
        DEFAULT_REDACTED_HEADERS.has(lowerKey) || extraRedactions.has(lowerKey);
      return [key, shouldRedact ? "[REDACTED]" : clampString(String(value), maxValueLength)];
    });
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function sanitizeUnknown(
  value: unknown,
  options: Pick<
    StimpactClientOptions,
    "includeBodies" | "redactedHeaders" | "maxValueLength"
  >,
  seen = new WeakSet<object>(),
  depth = 0,
): unknown {
  const maxValueLength = options.maxValueLength ?? 2_048;
  if (value == null || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return clampString(value, maxValueLength);
  }
  if (typeof value === "bigint") {
    return clampString(value.toString(), maxValueLength);
  }
  if (typeof value === "function" || typeof value === "symbol") {
    return clampString(String(value), maxValueLength);
  }
  if (depth >= 4) {
    return "[TRUNCATED]";
  }
  if (Array.isArray(value)) {
    return value
      .slice(0, 20)
      .map((item) => sanitizeUnknown(item, options, seen, depth + 1));
  }
  if (typeof value === "object") {
    if (seen.has(value as object)) {
      return "[Circular]";
    }
    seen.add(value as object);
    const output: Record<string, unknown> = {};
    for (const [key, entry] of Object.entries(value as Record<string, unknown>).slice(0, 25)) {
      output[key] = sanitizeUnknown(entry, options, seen, depth + 1);
    }
    return output;
  }
  return clampString(String(value), maxValueLength);
}

function safeSerialize(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function clampString(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...[truncated]`;
}

function omitUndefined<T extends Record<string, unknown>>(value: T): T | undefined {
  const entries = Object.entries(value).filter(([, entry]) => entry !== undefined);
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries) as T;
}

function resolveTokenExpiryMs(response: BrowserTokenResponse | null): number {
  if (typeof response?.expires_at === "string") {
    const parsed = Date.parse(response.expires_at);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  if (typeof response?.expires_in_seconds === "number" && Number.isFinite(response.expires_in_seconds)) {
    return Date.now() + Math.max(30, response.expires_in_seconds) * 1_000;
  }
  return Date.now() + 60_000;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

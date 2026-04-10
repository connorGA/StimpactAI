import type {
  BrowserAutoCaptureOptions,
  BrowserCaptureSubscription,
  CaptureErrorInput,
  HeartbeatInput,
  HeartbeatSubscription,
  StimpactClientOptions,
  StimpactEnvironment,
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
  timestamp: string;
};

type HeartbeatPayload = {
  project_id: string;
  environment: StimpactEnvironment;
  service: string;
  commit_sha?: string | null;
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
      | "captureRequestContext"
      | "captureResponseContext"
      | "includeBodies"
      | "redactedHeaders"
      | "maxValueLength"
    >
  > &
    Pick<
      StimpactClientOptions,
      | "apiKey"
      | "browserKey"
      | "browserTokenEndpoint"
      | "tokenProvider"
      | "environment"
      | "fetchImpl"
      | "headers"
    >;
  private cachedBrowserToken: string | null = null;
  private cachedBrowserTokenExpiresAtMs = 0;
  private browserTokenPromise: Promise<string> | null = null;

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
      captureRequestContext: options.captureRequestContext ?? false,
      captureResponseContext: options.captureResponseContext ?? false,
      includeBodies: options.includeBodies ?? false,
      redactedHeaders: options.redactedHeaders ?? [],
      maxValueLength: options.maxValueLength ?? 2_048,
    };
  }

  async captureError(input: CaptureErrorInput): Promise<void> {
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
      timestamp: normalizeTimestamp(input.timestamp),
    };

    await this.sendTelemetry(payload);
  }

  async sendHeartbeat(input: HeartbeatInput = {}): Promise<void> {
    const payload: HeartbeatPayload = {
      project_id: this.options.projectId,
      environment: input.environment ?? this.options.environment ?? "production",
      service: input.service ?? this.options.service,
      commit_sha: input.commitSha ?? null,
      timestamp: normalizeTimestamp(input.timestamp),
    };
    await this.sendHeartbeatPayload(payload);
  }

  startHeartbeat(options: HeartbeatInput & { intervalMs?: number } = {}): HeartbeatSubscription {
    const intervalMs = options.intervalMs ?? 300_000;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    void this.sendHeartbeat(options);
    if (typeof setInterval !== "undefined") {
      intervalId = setInterval(() => {
        void this.sendHeartbeat(options);
      }, intervalMs);
    }
    return {
      dispose: () => {
        if (intervalId !== null && typeof clearInterval !== "undefined") {
          clearInterval(intervalId);
        }
      },
    };
  }

  async wrapAsync<T>(
    operation: () => Promise<T>,
    context?: Omit<CaptureErrorInput, "error">,
  ): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      try {
        await this.captureError({
          ...context,
          error,
        });
      } catch (captureFailure) {
        if (error instanceof Error) {
          Object.defineProperty(error, "captureFailure", {
            value: captureFailure,
            configurable: true,
          });
        }
      }
      throw error;
    }
  }

  registerBrowserAutoCapture(
    options: BrowserAutoCaptureOptions = {},
  ): BrowserCaptureSubscription {
    if (typeof window === "undefined") {
      return { dispose: () => undefined };
    }

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
      }).catch(() => undefined);
    };

    const rejectionListener = (event: PromiseRejectionEvent) => {
      if (this.shouldIgnoreAutoCapturedError(event.reason)) {
        return;
      }
      void this.captureError({
        error: event.reason ?? "Unhandled promise rejection",
        service: this.options.service,
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

  private shouldIgnoreAutoCapturedError(error: unknown): boolean {
    return error instanceof StimpactRequestError;
  }

  private async sendTelemetry(payload: TelemetryPayload): Promise<void> {
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
    return token;
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
}

function normalizeTimestamp(value: string | Date | undefined): string {
  if (!value) {
    return new Date().toISOString();
  }
  return value instanceof Date ? value.toISOString() : value;
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

import type {
  BrowserAutoCaptureOptions,
  BrowserCaptureSubscription,
  CaptureErrorInput,
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

type NormalizedError = {
  message: string;
  stacktrace: string;
};

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
      | "apiKey"
      | "service"
      | "timeoutMs"
      | "retryAttempts"
      | "retryDelayMs"
    >
  > &
    Pick<StimpactClientOptions, "environment" | "fetchImpl" | "headers">;

  constructor(options: StimpactClientOptions) {
    this.options = {
      ...options,
      baseUrl: options.baseUrl.replace(/\/$/, ""),
      environment: options.environment ?? "production",
      fetchImpl: options.fetchImpl ?? fetch,
      headers: options.headers ?? {},
      timeoutMs: options.timeoutMs ?? 5_000,
      retryAttempts: options.retryAttempts ?? 2,
      retryDelayMs: options.retryDelayMs ?? 250,
    };
  }

  async captureError(input: CaptureErrorInput): Promise<void> {
    const normalized = normalizeError(input.error);
    const payload: TelemetryPayload = {
      project_id: this.options.projectId,
      environment: input.environment ?? this.options.environment ?? "production",
      service: input.service ?? this.options.service,
      error_message: normalized.message,
      stacktrace: normalized.stacktrace,
      request: input.request,
      response: input.response,
      commit_sha: input.commitSha ?? null,
      timestamp: normalizeTimestamp(input.timestamp),
    };

    await this.sendTelemetry(payload);
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
      void this.captureError({
        error: event.error ?? event.message,
        service: this.options.service,
      });
    };

    const rejectionListener = (event: PromiseRejectionEvent) => {
      void this.captureError({
        error: event.reason ?? "Unhandled promise rejection",
        service: this.options.service,
      });
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

  private async sendTelemetryOnce(payload: TelemetryPayload): Promise<void> {
    const fetchImpl = this.options.fetchImpl ?? fetch;
    const controller =
      typeof AbortController === "undefined" ? null : new AbortController();
    const timeout = controller
      ? setTimeout(() => controller.abort(), this.options.timeoutMs)
      : null;

    try {
      const response = await fetchImpl(`${this.options.baseUrl}/telemetry/error`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Stimpact-Project-Key": this.options.apiKey,
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
}

function normalizeTimestamp(value: string | Date | undefined): string {
  if (!value) {
    return new Date().toISOString();
  }
  return value instanceof Date ? value.toISOString() : value;
}

function normalizeError(error: unknown): NormalizedError {
  if (error instanceof Error) {
    return {
      message: error.message || error.name || "Unknown error",
      stacktrace: error.stack || error.message || error.name,
    };
  }
  if (typeof error === "string") {
    return {
      message: error,
      stacktrace: error,
    };
  }
  return {
    message: "Unknown error",
    stacktrace: JSON.stringify(error, null, 2),
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

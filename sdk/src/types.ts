export type StimpactEnvironment =
  | "production"
  | "staging"
  | "development"
  | "test";

export type StimpactTokenProvider = () => Promise<string>;

export type HttpRequestContext = {
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  body?: unknown;
};

export type HttpResponseContext = {
  status_code?: number;
  headers?: Record<string, string>;
  body?: unknown;
};

export type CaptureErrorInput = {
  error: unknown;
  request?: HttpRequestContext;
  response?: HttpResponseContext;
  commitSha?: string | null;
  environment?: StimpactEnvironment;
  service?: string;
  timestamp?: string | Date;
  /**
   * Whether the error was caught/handled by application code before being
   * reported. When `true`, the backend treats this as a user-facing outcome
   * (e.g. a wrong-password response) and is much less likely to trigger an
   * autonomous repair run. When `false`, the error is treated as an
   * uncaught/unhandled failure. If omitted, the backend falls back to its own
   * heuristics.
   */
  handled?: boolean;
};

export type ErrorCaptureContext = Omit<CaptureErrorInput, "error">;

export type HeartbeatInput = {
  commitSha?: string | null;
  environment?: StimpactEnvironment;
  service?: string;
  timestamp?: string | Date;
};

export type HeartbeatScheduleOptions = HeartbeatInput & {
  intervalMs?: number;
  immediate?: boolean;
  jitterRatio?: number;
  pauseWhenHidden?: boolean;
  skipWhenOffline?: boolean;
};

export type StimpactClientOptions = {
  baseUrl: string;
  projectId: string;
  apiKey?: string;
  browserKey?: string;
  browserTokenEndpoint?: string;
  tokenProvider?: StimpactTokenProvider;
  service: string;
  environment?: StimpactEnvironment;
  fetchImpl?: typeof fetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  retryAttempts?: number;
  retryDelayMs?: number;
  browserTokenFailureCooldownMs?: number;
  captureRequestContext?: boolean;
  captureResponseContext?: boolean;
  includeBodies?: boolean;
  redactedHeaders?: string[];
  maxValueLength?: number;
};

export type BrowserAutoCaptureOptions = {
  captureWindowErrors?: boolean;
  captureUnhandledRejections?: boolean;
};

export type BrowserCaptureSubscription = {
  dispose: () => void;
};

export type ProcessListenerTarget = {
  on?: (event: string, listener: (...args: unknown[]) => void) => void;
  off?: (event: string, listener: (...args: unknown[]) => void) => void;
  addListener?: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
};

export type ProcessAutoCaptureOptions = {
  captureUncaughtExceptions?: boolean;
  captureUnhandledRejections?: boolean;
  processTarget?: ProcessListenerTarget | null;
};

export type ProcessCaptureSubscription = {
  dispose: () => void;
};

export type HeartbeatSubscription = {
  dispose: () => void;
  pause: () => void;
  resume: () => void;
  triggerNow: (input?: HeartbeatInput) => Promise<void>;
  isRunning: () => boolean;
};

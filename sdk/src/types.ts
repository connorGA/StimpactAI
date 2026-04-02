export type StimpactEnvironment =
  | "production"
  | "staging"
  | "development"
  | "test";

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
};

export type HeartbeatInput = {
  commitSha?: string | null;
  environment?: StimpactEnvironment;
  service?: string;
  timestamp?: string | Date;
};

export type StimpactClientOptions = {
  baseUrl: string;
  projectId: string;
  apiKey: string;
  service: string;
  environment?: StimpactEnvironment;
  fetchImpl?: typeof fetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  retryAttempts?: number;
  retryDelayMs?: number;
};

export type BrowserAutoCaptureOptions = {
  captureWindowErrors?: boolean;
  captureUnhandledRejections?: boolean;
};

export type BrowserCaptureSubscription = {
  dispose: () => void;
};

export type HeartbeatSubscription = {
  dispose: () => void;
};

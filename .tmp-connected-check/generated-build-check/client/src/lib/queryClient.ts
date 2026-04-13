import { QueryClient, QueryFunction, MutationCache, QueryCache } from "@tanstack/react-query";
import { getAuthToken } from "./xanoClient";
import { captureHandledError } from "../stimpact";

async function reportHandledError(input: {
  error: unknown;
  request?: { method?: string; url?: string };
  response?: { status_code?: number };
}) {
  await captureHandledError(input);
}

async function throwIfResNotOk(
  res: Response,
  request?: { method?: string; url?: string },
) {
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    const error = new Error(`${res.status}: ${text}`);
    await reportHandledError({
      error,
      request,
      response: { status_code: res.status },
    });
    throw error;
  }
}

export async function apiRequest(
  method: string,
  url: string,
  data?: unknown | undefined,
): Promise<Response> {
  const headers: Record<string, string> = data ? { "Content-Type": "application/json" } : {};
  
  // Add auth token if available
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(url, {
      method,
      headers,
      body: data ? JSON.stringify(data) : undefined,
      credentials: "include",
    });

    await throwIfResNotOk(res, { method, url });
    return res;
  } catch (error) {
    await reportHandledError({
      error,
      request: { method, url },
    });
    throw error;
  }
}

type UnauthorizedBehavior = "returnNull" | "throw";
export const getQueryFn: <T>(options: {
  on401: UnauthorizedBehavior;
}) => QueryFunction<T> =
  ({ on401: unauthorizedBehavior }) =>
  async ({ queryKey }) => {
    const url = queryKey.join("/") as string;
    try {
      const res = await fetch(url, {
        credentials: "include",
      });

      if (unauthorizedBehavior === "returnNull" && res.status === 401) {
        return null;
      }

      await throwIfResNotOk(res, { method: "GET", url });
      return await res.json();
    } catch (error) {
      await reportHandledError({
        error,
        request: { method: "GET", url },
      });
      throw error;
    }
  };

function describeReactQueryKey(key: readonly unknown[] | undefined): string {
  if (!key || key.length === 0) {
    return "react-query";
  }
  return key
    .map((segment) => {
      if (typeof segment === "string" || typeof segment === "number") {
        return String(segment);
      }
      return "segment";
    })
    .join("/");
}

const stimpactQueryCache = new QueryCache({
  onError: (error, query) => {
    void reportHandledError({
      error,
      request: {
        method: "QUERY",
        url: describeReactQueryKey(query.queryKey),
      },
    });
  },
});

const stimpactMutationCache = new MutationCache({
  onError: (error, _variables, _context, mutation) => {
    const mutationKey = Array.isArray(mutation.options.mutationKey)
      ? describeReactQueryKey(mutation.options.mutationKey)
      : mutation.options.meta?.stimpactAction
        ? String(mutation.options.meta.stimpactAction)
        : "react-query-mutation";
    void reportHandledError({
      error,
      request: {
        method: "MUTATION",
        url: mutationKey,
      },
    });
  },
});

export const queryClient = new QueryClient({
  queryCache: stimpactQueryCache,
  mutationCache: stimpactMutationCache,
  defaultOptions: {
    queries: {
      queryFn: getQueryFn({ on401: "throw" }),
      refetchInterval: false,
      refetchOnWindowFocus: false,
      staleTime: Infinity,
      retry: false,
    },
    mutations: {
      retry: false,
    },
  },
});

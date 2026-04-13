import { MutationCache, QueryCache, QueryClient, QueryFunction } from "@tanstack/react-query";

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
    const error = new Error(`${res.status}: ${res.statusText}`);
    await reportHandledError({
      error,
      request,
      response: { status_code: res.status },
    });
    throw error;
  }
}

export const getQueryFn: <T>(options: {
  on401: "returnNull" | "throw";
}) => QueryFunction<T> =
  ({ on401: unauthorizedBehavior }) =>
  async ({ queryKey }) => {
    const url = queryKey.join("/") as string;
    const res = await fetch(url);
    if (unauthorizedBehavior === "returnNull" && res.status === 401) {
      return null as never;
    }
    await throwIfResNotOk(res, { method: "GET", url });
    return await res.json();
  };

function describeReactQueryKey(key: readonly unknown[] | undefined): string {
  if (!key || key.length === 0) {
    return "react-query";
  }
  return key.map((segment) => String(segment)).join("/");
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
      retry: false,
    },
    mutations: {
      retry: false,
    },
  },
});

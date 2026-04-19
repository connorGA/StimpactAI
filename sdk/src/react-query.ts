import { captureHandledError } from "./browser-runtime.js";

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

export function wrapQueryClient<T extends {
  getDefaultOptions?: () => Record<string, unknown>;
  setDefaultOptions?: (options: Record<string, unknown>) => void;
}>(queryClient: T): T {
  const existingDefaults = queryClient.getDefaultOptions?.() ?? {};
  const existingQueries = (existingDefaults.queries as Record<string, unknown> | undefined) ?? {};
  const existingMutations = (existingDefaults.mutations as Record<string, unknown> | undefined) ?? {};
  const previousQueryOnError = existingQueries.onError;
  const previousMutationOnError = existingMutations.onError;

  queryClient.setDefaultOptions?.({
    ...existingDefaults,
    queries: {
      ...existingQueries,
      onError: async (error: unknown, query: { queryKey?: readonly unknown[] }) => {
        await captureHandledError({
          error,
          request: {
            method: "QUERY",
            url: describeReactQueryKey(query?.queryKey),
          },
        });
        if (typeof previousQueryOnError === "function") {
          await previousQueryOnError(error, query);
        }
      },
    },
    mutations: {
      ...existingMutations,
      onError: async (
        error: unknown,
        _variables: unknown,
        _context: unknown,
        mutation: { options?: { mutationKey?: readonly unknown[]; meta?: Record<string, unknown> } },
      ) => {
        const mutationKey = Array.isArray(mutation?.options?.mutationKey)
          ? describeReactQueryKey(mutation.options?.mutationKey)
          : mutation?.options?.meta?.stimpactAction
            ? String(mutation.options.meta.stimpactAction)
            : "react-query-mutation";
        await captureHandledError({
          error,
          request: {
            method: "MUTATION",
            url: mutationKey,
          },
        });
        if (typeof previousMutationOnError === "function") {
          await previousMutationOnError(error, _variables, _context, mutation);
        }
      },
    },
  });

  return queryClient;
}

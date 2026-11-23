import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { isApiError } from '@/api/errors';

/**
 * Shared query client. `onUnauthorized` runs when any request reports an ended session (401),
 * so the app can send the user back to the sign-in page.
 */
export function createQueryClient(onUnauthorized?: () => void): QueryClient {
  const handleError = (error: unknown) => {
    if (onUnauthorized && isApiError(error) && error.status === 401) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleError }),
    mutationCache: new MutationCache({ onError: handleError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => !(isApiError(error) && error.status > 0 && error.status < 500) && failureCount < 2,
      },
      mutations: { retry: false },
    },
  });
}

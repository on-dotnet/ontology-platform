import type { QueryClient } from '@tanstack/react-query';
import { createRouter, type RouterHistory } from '@tanstack/react-router';

import { RouteErrorState } from '@/features/errors/route-error-state';
import { routeTree } from '@/routeTree.gen';

interface CreateAppRouterOptions {
  queryClient: QueryClient;
  /** Memory history in tests; browser history by default. */
  history?: RouterHistory;
}

export function createAppRouter({ queryClient, history }: CreateAppRouterOptions) {
  return createRouter({
    routeTree,
    context: { queryClient },
    ...(history ? { history } : {}),
    defaultPreload: 'intent',
    // Data freshness is managed by TanStack Query.
    defaultPreloadStaleTime: 0,
    defaultPendingMs: 300,
    defaultPendingMinMs: 200,
    defaultErrorComponent: RouteErrorState,
    scrollRestoration: true,
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}

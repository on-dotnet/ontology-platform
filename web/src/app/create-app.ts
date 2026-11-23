import type { RouterHistory } from '@tanstack/react-router';

import { clearSession } from '@/features/auth/api';
import { createAppRouter } from '@/router';

import { createQueryClient } from './query-client';

/** Builds the query client and router with the app-wide "session ended" handling. */
export function createApp(history?: RouterHistory) {
  const queryClient = createQueryClient(() => {
    // A request reported an ended session: forget the user, sign in again, then return here.
    // Only invoked after startup, so `router` is initialized by then.
    if (router.state.location.pathname === '/login') return;
    clearSession(queryClient);
    void router.navigate({ to: '/login', search: { redirect: router.state.location.href } });
  });
  const router = createAppRouter({ queryClient, ...(history ? { history } : {}) });
  return { queryClient, router };
}

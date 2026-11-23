import { createFileRoute, redirect } from '@tanstack/react-router';

import { AppShell } from '@/components/layout/app-shell';
import { meQueryOptions } from '@/features/auth/api';
import { AppErrorPage, AppShellSkeleton } from '@/features/errors/standalone-pages';

/** Pathless layout for every signed-in page: checks the session, then renders the shell. */
export const Route = createFileRoute('/_app')({
  beforeLoad: async ({ context, location }) => {
    const user = await context.queryClient.ensureQueryData(meQueryOptions());
    if (!user) throw redirect({ to: '/login', search: { redirect: location.href } });
  },
  pendingComponent: AppShellSkeleton,
  errorComponent: AppErrorPage,
  component: AppShell,
});

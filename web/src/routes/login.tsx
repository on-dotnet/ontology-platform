import { useQueryClient } from '@tanstack/react-query';
import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router';

import { meQueryKey, meQueryOptions, type UserInfo } from '@/features/auth/api';
import { LoginPage } from '@/features/auth/login-page';
import { safeRedirect } from '@/features/auth/redirect';

interface LoginSearch {
  redirect?: string;
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): LoginSearch => {
    const target = safeRedirect(search.redirect);
    return target ? { redirect: target } : {};
  },
  beforeLoad: async ({ context, search }) => {
    // Already signed in: skip the form. A failing session check just shows the form.
    const user = await context.queryClient.ensureQueryData(meQueryOptions()).catch(() => null);
    if (user) throw redirect({ href: search.redirect ?? '/', replace: true });
  },
  component: LoginRoute,
});

function LoginRoute() {
  const { redirect: target } = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const onSuccess = async (user: UserInfo) => {
    queryClient.setQueryData(meQueryKey, user);
    await navigate({ href: target ?? '/', replace: true });
  };

  return <LoginPage onSuccess={onSuccess} />;
}

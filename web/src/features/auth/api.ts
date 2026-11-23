import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/schema';

export type UserInfo = components['schemas']['UserInfo'];
export type Role = components['schemas']['Role'];
export type LoginRequest = components['schemas']['LoginRequest'];

export const meQueryKey = ['auth', 'me'] as const;

/** Current user, or `null` when not signed in (401). Other failures throw. */
export async function fetchMe(): Promise<UserInfo | null> {
  try {
    return await unwrap(api.GET('/api/auth/me'));
  } catch (error) {
    if (isApiError(error) && error.status === 401) return null;
    throw error;
  }
}

export function meQueryOptions() {
  return queryOptions({
    queryKey: meQueryKey,
    queryFn: fetchMe,
    // Session changes are pushed into the cache by login/logout and the global 401 handler.
    staleTime: Infinity,
    retry: false,
  });
}

export function useCurrentUser(): UserInfo | null {
  return useQuery(meQueryOptions()).data ?? null;
}

export function login(credentials: LoginRequest): Promise<UserInfo> {
  return unwrap(api.POST('/api/auth/login', { body: credentials }));
}

/** Ends the session. A 401 means it had already ended, which is the outcome the user asked for. */
export async function logout(): Promise<void> {
  try {
    await unwrapEmpty(api.POST('/api/auth/logout'));
  } catch (error) {
    if (isApiError(error) && error.status === 401) return;
    throw error;
  }
}

/** Marks the session as ended in the cache; the router then treats the user as signed out. */
export function clearSession(queryClient: QueryClient): void {
  queryClient.setQueryData(meQueryKey, null);
}

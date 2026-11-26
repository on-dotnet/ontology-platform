import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import { isForbidden } from '@/api/errors';
import type { components, operations } from '@/api/schema';
import { meQueryKey } from '@/features/auth/api';

export type AccessToken = components['schemas']['AccessToken'];
export type TokenInput = components['schemas']['AccessTokenCreate'];
export type TokenScope = TokenInput['scopes'][number];
type ListQuery = NonNullable<operations['list_tokens_api_auth_tokens_get']['parameters']['query']>;
export type OwnerView = NonNullable<ListQuery['owner']>;

export const tokenListKey = ['access-tokens'] as const;

export function useAccessTokens(userId: string, owner: OwnerView) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: [...tokenListKey, userId, owner],
    queryFn: async ({ signal }) => {
      try {
        return await unwrap(api.GET('/api/auth/tokens', { params: { query: { owner } }, signal }));
      } catch (error) {
        if (owner === 'all' && isForbidden(error)) void queryClient.invalidateQueries({ queryKey: meQueryKey });
        throw error;
      }
    },
  });
}

export function createToken(body: TokenInput) {
  return unwrap(api.POST('/api/auth/tokens', { body }));
}

export function revokeToken(id: string) {
  return unwrapEmpty(api.DELETE('/api/auth/tokens/{id}', { params: { path: { id } } }));
}

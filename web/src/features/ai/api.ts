import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type AiStatus = components['schemas']['AiStatus'];
export type AiHealth = 'available' | 'unreachable' | 'not_configured' | 'unknown';

export const aiStatusKey = ['ai', 'status'] as const;

/** Model access status; the server caches reachability for 60 seconds, so the client polls at that pace. */
export function useAiStatus() {
  return useQuery({
    queryKey: aiStatusKey,
    queryFn: () => unwrap(api.GET('/api/ai/status')),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function aiHealth(status: AiStatus): AiHealth {
  if (!status.configured) return 'not_configured';
  if (status.reachable === true) return 'available';
  if (status.reachable === false) return 'unreachable';
  return 'unknown';
}

/** True when AI analysis cannot run right now, so users must be told the impact. */
export function isAiDegraded(health: AiHealth): health is 'unreachable' | 'not_configured' {
  return health === 'unreachable' || health === 'not_configured';
}

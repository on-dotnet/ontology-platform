import { useInfiniteQuery } from '@tanstack/react-query';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import type { components } from '@/api/schema';

export type MemoryEntry = components['schemas']['ReviewMemoryEntry'];
export type MemoryPage = components['schemas']['ReviewMemoryPage'];
export type MemoryKind = MemoryEntry['kind'];

export const memoryKeys = { all: ['review-memory'] as const, list: (ontologyId: string, kind?: MemoryKind, q?: string) => ['review-memory', ontologyId, kind, q] as const };

export function useReviewMemory(ontologyId: string, kind?: MemoryKind, q?: string) {
  return useInfiniteQuery({
    queryKey: memoryKeys.list(ontologyId, kind, q),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => unwrap(api.GET('/api/ontologies/{id}/review-memory', {
      params: { path: { id: ontologyId }, query: { ...(kind ? { kind } : {}), ...(q ? { q } : {}), ...(pageParam ? { cursor: pageParam } : {}) } },
    })),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}

export function deleteMemory(ontologyId: string, entryId: string) {
  return unwrapEmpty(api.DELETE('/api/ontologies/{id}/review-memory/{entryId}', { params: { path: { id: ontologyId, entryId } } }));
}

export function restoreMemory(ontologyId: string, entryId: string) {
  return unwrap(api.POST('/api/ontologies/{id}/review-memory/{entryId}/restore', { params: { path: { id: ontologyId, entryId } } }));
}

export function clearMemory(ontologyId: string) {
  return unwrap(api.POST('/api/ontologies/{id}/review-memory/clear', { params: { path: { id: ontologyId } } }));
}

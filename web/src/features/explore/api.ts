import { hashKey, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { components } from '@/api/schema';
import { ontologyKeys } from '@/features/ontologies/api';

type Release = components['schemas']['ReleaseRef'];
type ObjectSearch = components['schemas']['ObjectSearch'];
type Relation = components['schemas']['ObjectRelation'];

function useExploreQuery<T>(queryKey: QueryKey, load: (signal: AbortSignal) => Promise<T>) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => load(signal),
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  // React Query owns the AbortController. Cancelling this exact key aborts fetch and reverts its state.
  return { ...query, requestKey: hashKey(queryKey), cancel: () => void client.cancelQueries({ queryKey, exact: true }) };
}

export function useExploreOntologies() {
  return useExploreQuery(ontologyKeys.list(), (signal) => unwrap(api.GET('/api/ontologies', { signal })));
}

export function useTypes(id: string, refresh: number) {
  return useExploreQuery(['explore', id, 'types', refresh], (signal) =>
    unwrap(api.GET('/api/ontologies/{id}/objects/types', { params: { path: { id } }, signal })),
  );
}

// Even a successful first-page or detail request can race publication after the types were loaded.
async function atRelease<T extends { release: Release }>(id: string, request: Promise<T>): Promise<T> {
  const result = await request;
  if (result.release.id !== id) throw new ApiError({ status: 409, code: 'query.release_changed' });
  return result;
}

export function useSearch(id: string, releaseId: string, body: ObjectSearch) {
  return useExploreQuery(['explore', id, releaseId, 'search', body], (signal) =>
    atRelease(releaseId, unwrap(api.POST('/api/ontologies/{id}/objects/search', { params: { path: { id } }, body, signal }))),
  );
}

export function useDetail(id: string, releaseId: string, typeId: string, key: string) {
  return useExploreQuery(['explore', id, releaseId, 'detail', typeId, key], (signal) =>
    atRelease(releaseId, unwrap(api.GET('/api/ontologies/{id}/objects/{typeId}/{key}', {
      params: { path: { id, typeId, key } }, signal,
    }))),
  );
}

export function useRelated(id: string, releaseId: string, typeId: string, key: string, relation: Relation, cursor: string | null) {
  const { relationId, direction } = relation;
  return useExploreQuery(['explore', id, releaseId, 'related', typeId, key, relationId, direction, cursor], (signal) =>
    atRelease(releaseId, unwrap(api.GET('/api/ontologies/{id}/objects/{typeId}/{key}/related', {
      params: { path: { id, typeId, key }, query: { relationId, direction, limit: 50, cursor: cursor ?? undefined } }, signal,
    }))),
  );
}

import { hashKey, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import { ApiError, isApiError } from '@/api/errors';
import type { components } from '@/api/schema';

type Release = components['schemas']['ReleaseRef'];
export const sampleLimit = 50;
const catalogKey = (id: string) => ['metrics', id, 'catalog'] as const;
const noRelease = (error: unknown) => isApiError(error) && error.code === 'query.no_release';

function useRead<T>(queryKey: QueryKey, load: (signal: AbortSignal) => Promise<T>, enabled = true) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey, queryFn: ({ signal }) => load(signal), enabled,
    retry: false, staleTime: 0, refetchOnWindowFocus: false,
  });
  return { ...query, requestKey: hashKey(queryKey), cancel: () => void client.cancelQueries({ queryKey, exact: true }) };
}

export function useMetricsCatalog(id: string) {
  return useRead(catalogKey(id), async (signal) => {
    const options = { params: { path: { id } }, signal };
    try {
      const [metrics, types] = await Promise.all([
        unwrap(api.GET('/api/ontologies/{id}/metrics', options)),
        unwrap(api.GET('/api/ontologies/{id}/objects/types', options)),
      ]);
      if (metrics.release.id !== types.release.id) throw new ApiError({ status: 409, code: 'query.release_changed' });
      return { release: metrics.release, metrics: metrics.items, types: types.items };
    } catch (error) {
      if (noRelease(error)) return null;
      throw error;
    }
  });
}

type Catalog = NonNullable<ReturnType<typeof useMetricsCatalog>['data']>;

function useReleasedResult<T extends { release: Release }>(
  id: string, releaseId: string, key: readonly string[], enabled: boolean, load: (signal: AbortSignal) => Promise<T>,
  isAvailable: (catalog: Catalog) => boolean,
) {
  const client = useQueryClient();
  const queryKey = ['metrics', id, releaseId, ...key];
  const query = useRead(queryKey, async (signal) => {
    try {
      const result = await load(signal);
      if (result.release.id !== releaseId) throw new ApiError({ status: 409, code: 'query.release_changed' });
      return result;
    } catch (error) {
      // A release can disappear between loading the two cards and submitting a check.
      if (!signal.aborted && noRelease(error)) client.setQueryData(catalogKey(id), null);
      throw error;
    }
  }, enabled);
  const retryWithCatalog = async () => {
    const catalog = catalogKey(id);
    await client.refetchQueries({ queryKey: catalog, exact: true }, { cancelRefetch: false });
    const latest = client.getQueryState<Catalog | null>(catalog);
    // A new release changes the observed key and starts the request itself.
    if (latest?.status === 'success' && latest.data?.release.id === releaseId && isAvailable(latest.data)) {
      await client.refetchQueries({ queryKey, exact: true, type: 'active' }, { cancelRefetch: false });
    }
  };
  return { ...query, retryWithCatalog };
}

export function useMetricValue(id: string, releaseId: string, metricId: string, enabled: boolean) {
  return useReleasedResult(id, releaseId, ['evaluate', metricId], enabled, (signal) =>
    unwrap(api.POST('/api/ontologies/{id}/metrics/{metricId}/evaluate', { params: { path: { id, metricId } }, body: {}, signal })),
    (catalog) => catalog.metrics.some((metric) => metric.metricId === metricId),
  );
}

export function useRuleReport(id: string, releaseId: string, typeId: string, language: string, enabled: boolean) {
  return useReleasedResult(id, releaseId, ['rules', typeId, language], enabled, (signal) =>
    unwrap(api.POST('/api/ontologies/{id}/rules/check', {
      params: { path: { id } }, body: { typeId, limit: sampleLimit }, headers: { 'Accept-Language': language }, signal,
    })),
    (catalog) => catalog.types.some((type) => type.typeId === typeId && !type.problem),
  );
}

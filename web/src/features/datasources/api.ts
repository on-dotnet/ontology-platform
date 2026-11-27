import { useQuery, type QueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type DataSource = components['schemas']['DataSource'];
export const listKey = ['data-sources', 'list'] as const;
export const sourceKey = (id: string) => ['data-sources', id] as const;

export function useSourceList() {
  return useQuery({
    queryKey: listKey,
    refetchOnMount: 'always',
    queryFn: ({ signal }) => unwrap(api.GET('/api/data-sources', { signal })),
  });
}

export function useSource(id: string, canBrowse: boolean) {
  return useQuery({
    queryKey: sourceKey(id),
    refetchOnMount: 'always',
    queryFn: ({ signal }) => unwrap(api.GET('/api/data-sources/{id}', { params: { path: { id } }, signal })),
    refetchInterval: ({ state: { data } }) =>
      canBrowse && data?.status === 'active' && data.catalog?.status === 'refreshing' ? 1000 : false,
  });
}

export async function testSavedSource(client: QueryClient, id: string) {
  try {
    return await unwrap(api.POST('/api/data-sources/{id}/test', { params: { path: { id } } }));
  } finally {
    await Promise.all([
      client.invalidateQueries({ queryKey: sourceKey(id), exact: true }),
      client.invalidateQueries({ queryKey: listKey }),
    ]);
  }
}

export async function rememberSource(client: QueryClient, source: DataSource) {
  // Polls and mutation responses can arrive after a newer edit or archive.
  const key = sourceKey(source.id);
  await client.cancelQueries({ queryKey: key, exact: true });
  client.setQueryData<DataSource>(key, (current) =>
    current && current.revision > source.revision ? current : source,
  );
  await client.invalidateQueries({ queryKey: listKey });
}

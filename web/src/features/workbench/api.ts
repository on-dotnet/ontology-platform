import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type WorkbenchSummary = components['schemas']['WorkbenchSummary'];
export type Activity = WorkbenchSummary['recentActivity'][number];

export const workbenchKeys = { summary: ['workbench', 'summary'] as const };

/** Refreshes every 5 seconds while documents are being processed, so the counts follow the pipeline. */
export function useWorkbenchSummary() {
  return useQuery({
    queryKey: workbenchKeys.summary,
    queryFn: () => unwrap(api.GET('/api/workbench/summary')),
    refetchInterval: (query) => ((query.state.data?.processingDocuments ?? 0) > 0 ? 5_000 : false),
  });
}

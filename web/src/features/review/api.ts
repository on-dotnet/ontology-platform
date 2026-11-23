import { useQuery, type QueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type ChangeSetSummary = components['schemas']['ChangeSetSummary'];
export type ChangeSetDetail = components['schemas']['ChangeSetDetail'];
export type ChangeItem = components['schemas']['ChangeItem'];
export type ElementFields = components['schemas']['ElementFields'];
export type Decision = ChangeItem['decision'];
export type ChangeOp = ChangeItem['op'];
export type ChangeSetSource = ChangeSetDetail['source'];
export type ItemFlag = ChangeItem['flags'][number];
export type ItemPatch = components['schemas']['ItemDecisionPatch'];
export type MergeResult = components['schemas']['MergeResult'];
export type SkipCode = MergeResult['skipped'][number]['code'];

export const changeSetKeys = {
  all: ['change-sets'] as const,
  list: (ontologyId: string) => [...changeSetKeys.all, 'list', ontologyId] as const,
  detail: (id: string) => [...changeSetKeys.all, 'detail', id] as const,
};

export function useChangeSets(ontologyId: string) {
  return useQuery({
    queryKey: changeSetKeys.list(ontologyId),
    queryFn: () => unwrap(api.GET('/api/change-sets', { params: { query: { ontologyId } } })),
  });
}

export function useChangeSet(id: string) {
  return useQuery({
    queryKey: changeSetKeys.detail(id),
    queryFn: () => unwrap(api.GET('/api/change-sets/{id}', { params: { path: { id } } })),
  });
}

export function patchItem(changeSetId: string, itemId: string, body: ItemPatch): Promise<ChangeItem> {
  return unwrap(api.PATCH('/api/change-sets/{id}/items/{itemId}', { params: { path: { id: changeSetId, itemId } }, body }));
}

export async function decideItems(changeSetId: string, itemIds: string[], decision: Decision): Promise<void> {
  await unwrap(api.POST('/api/change-sets/{id}/decisions', { params: { path: { id: changeSetId } }, body: { itemIds, decision } }));
}

export function mergeChangeSet(changeSetId: string): Promise<MergeResult> {
  return unwrap(api.POST('/api/change-sets/{id}/merge', { params: { path: { id: changeSetId } } }));
}

/** Writes an updated item into the cached change set and recomputes the decision counts. */
export function replaceItemInCache(queryClient: QueryClient, changeSetId: string, item: ChangeItem): void {
  queryClient.setQueryData<ChangeSetDetail>(changeSetKeys.detail(changeSetId), (current) => {
    if (!current) return current;
    const items = current.items.map((existing) => (existing.id === item.id ? item : existing));
    return { ...current, items, counts: countDecisions(items) };
  });
}

export function countDecisions(items: readonly Pick<ChangeItem, 'decision'>[]): ChangeSetDetail['counts'] {
  return {
    total: items.length,
    pending: items.filter((item) => item.decision === 'pending').length,
    accepted: items.filter((item) => item.decision === 'accepted').length,
    rejected: items.filter((item) => item.decision === 'rejected').length,
  };
}

/** Change sets proposed by AI: their items carry the AI label, confidence and evidence. */
export function isAiSource(source: ChangeSetSource): boolean {
  return source === 'ai_extraction' || source === 'ai_assistant';
}

/** Sources reviewed as a whole: imports and manual edits offer "accept all". */
export function acceptsAll(source: ChangeSetSource): boolean {
  return source === 'import' || source === 'manual';
}

/** Confidence tier boundaries (ui-guidelines §7: high / medium / low). */
export const HIGH_CONFIDENCE = 0.8;
export const MEDIUM_CONFIDENCE = 0.5;

export type ConfidenceTier = 'high' | 'medium' | 'low';

export function confidenceTier(confidence: number): ConfidenceTier {
  if (confidence >= HIGH_CONFIDENCE) return 'high';
  if (confidence >= MEDIUM_CONFIDENCE) return 'medium';
  return 'low';
}

/** Pending items safe to accept in bulk: confidence ≥ 0.8 and no flags. */
export function highConfidencePending(items: readonly ChangeItem[]): ChangeItem[] {
  return items.filter(
    (item) => item.decision === 'pending' && item.confidence !== null && item.confidence >= HIGH_CONFIDENCE && item.flags.length === 0,
  );
}

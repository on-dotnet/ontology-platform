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
export type ItemResolution = NonNullable<ChangeItem['resolution']>;
export type ItemMatch = NonNullable<ChangeItem['match']>;
export type MatchDecision = ItemMatch['decision'];
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

/** The decisions endpoint takes at most this many items per request. */
export const DECISION_BATCH_SIZE = 5000;

/** Some batches were saved before one failed; the saved ones stay decided, so a retry sends only the rest. */
export class PartialDecisionError extends Error {
  readonly saved: number;
  readonly total: number;
  readonly reason: unknown;

  constructor(saved: number, total: number, reason: unknown) {
    super(`Saved ${saved} of ${total} decisions`);
    this.name = 'PartialDecisionError';
    this.saved = saved;
    this.total = total;
    this.reason = reason;
  }
}

/** Sends the decisions in batches, one after another, and stops at the first batch that fails. */
export async function decideItems(changeSetId: string, itemIds: string[], decision: Decision): Promise<void> {
  for (let start = 0; start < itemIds.length; start += DECISION_BATCH_SIZE) {
    const batch = itemIds.slice(start, start + DECISION_BATCH_SIZE);
    try {
      await unwrap(api.POST('/api/change-sets/{id}/decisions', { params: { path: { id: changeSetId } }, body: { itemIds: batch, decision } }));
    } catch (error) {
      if (start === 0) throw error;
      throw new PartialDecisionError(start, itemIds.length, error);
    }
  }
}

/**
 * Merges with the token of the detail the reviewer was shown. If the working version changed so
 * that the merge would now do something else, the server refuses it (409 `changeset.resolution_changed`).
 */
export function mergeChangeSet(changeSetId: string, resolutionToken: string): Promise<MergeResult> {
  return unwrap(api.POST('/api/change-sets/{id}/merge', { params: { path: { id: changeSetId } }, body: { resolutionToken } }));
}

/** A merge would not add the item as proposed: it goes into an existing element or is renamed. */
export function mergesDifferently(item: ChangeItem): boolean {
  return item.op === 'create' && item.resolution !== null && item.resolution.mode !== 'create';
}

/** Rejects the whole change set; its creator may do so to withdraw it, whatever their role. */
export function rejectChangeSet(changeSetId: string): Promise<ChangeSetSummary> {
  return unwrap(api.POST('/api/change-sets/{id}/reject', { params: { path: { id: changeSetId } } }));
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
  return source === 'ai_extraction' || source === 'ai_assistant' || source === 'ai_binding';
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

/**
 * Pending items safe to accept in bulk: confidence ≥ 0.8 and no flags. Items a merge would not add as
 * proposed (into an existing element, renamed), items with an alignment record and restores are decided
 * one by one (spec 004, 5.4).
 */
export function highConfidencePending(items: readonly ChangeItem[]): ChangeItem[] {
  return items.filter(
    (item) =>
      item.decision === 'pending' &&
      item.confidence !== null &&
      item.confidence >= HIGH_CONFIDENCE &&
      item.flags.length === 0 &&
      !mergesDifferently(item) &&
      item.match === null &&
      item.op !== 'restore',
  );
}

/**
 * Pending items recorded as the same concept as an element or another item, unless a reviewer
 * kept the two apart: offered as one explicit bulk accept that lists where each goes (spec 004, 5.4).
 */
export function sameConceptPending(items: readonly ChangeItem[]): (ChangeItem & { match: ItemMatch })[] {
  return items.filter(
    (item): item is ChangeItem & { match: ItemMatch } =>
      item.decision === 'pending' && item.match?.kind === 'same' && item.match.decision !== 'different' && !item.match.keptApart,
  );
}

export type MatchPlace = 'element' | 'sameChangeSet' | 'otherChangeSet';

/**
 * Where the other side of a record is: an element of the working version, or an item of this or
 * another change set. A record synthesized from a merged item names that item's change set.
 */
export function matchPlace(match: ItemMatch, changeSetId: string): MatchPlace {
  if (match.itemId === null || match.changeSetId === null) return 'element';
  return match.changeSetId === changeSetId ? 'sameChangeSet' : 'otherChangeSet';
}

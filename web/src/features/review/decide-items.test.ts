import { describe, expect, it } from 'vitest';

import { ApiError } from '@/api/errors';
import { jsonResponse, mockFetch, problemResponse, requestAt } from '@/test/utils';

import { DECISION_BATCH_SIZE, PartialDecisionError, decideItems } from './api';

const ids = (count: number) => Array.from({ length: count }, (_, index) => `item-${String(index)}`);

async function sentBatches(fetchMock: ReturnType<typeof mockFetch>): Promise<string[][]> {
  const batches: string[][] = [];
  for (let index = 0; index < fetchMock.mock.calls.length; index += 1) {
    const body = (await requestAt(fetchMock, index).json()) as { itemIds: string[] };
    batches.push(body.itemIds);
  }
  return batches;
}

describe('decideItems batches', () => {
  it('sends nothing for no items', async () => {
    const fetchMock = mockFetch(() => jsonResponse({}));
    await decideItems('cs-1', [], 'accepted');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends exactly one batch for 5000 items and two for 5001', async () => {
    expect(DECISION_BATCH_SIZE).toBe(5000);

    const full = mockFetch(() => jsonResponse({}));
    await decideItems('cs-1', ids(5000), 'accepted');
    expect((await sentBatches(full)).map((batch) => batch.length)).toEqual([5000]);

    const over = mockFetch(() => jsonResponse({}));
    await decideItems('cs-1', ids(5001), 'rejected');
    const batches = await sentBatches(over);
    expect(batches.map((batch) => batch.length)).toEqual([5000, 1]);
    expect(batches[1]).toEqual(['item-5000']);
  });

  it('rethrows the original error when the first batch fails and sends no more', async () => {
    const fetchMock = mockFetch(() => problemResponse(503, 'service.unavailable'));
    const error: unknown = await decideItems('cs-1', ids(5001), 'accepted').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(PartialDecisionError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

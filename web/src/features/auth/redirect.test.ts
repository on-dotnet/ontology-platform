import { describe, expect, it } from 'vitest';

import { safeRedirect } from './redirect';

const origin = 'https://ontology.example';

describe('safeRedirect', () => {
  it.each([
    ['/review', '/review'],
    ['/documents?tab=parsed#top', '/documents?tab=parsed#top'],
    ['/a/../settings', '/settings'],
    [`${origin}/explore`, '/explore'],
  ])('keeps the same-origin path of %j', (value, expected) => {
    expect(safeRedirect(value, origin)).toBe(expected);
  });

  it.each([
    ['/\t/evil.example'],
    ['//evil.example'],
    ['/\\evil.example'],
    ['https://evil.example'],
    ['https://evil.example/review'],
    ['javascript:alert(1)'],
    ['/.//evil.example'],
    ['/login'],
    ['/login?redirect=%2Freview'],
    [''],
    [42],
    [undefined],
  ])('rejects %j', (value) => {
    expect(safeRedirect(value, origin)).toBeUndefined();
  });
});

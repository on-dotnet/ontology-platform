import { describe, expect, it } from 'vitest';

import { axiomFixture } from '@/test/fixtures';

import { pageGroups, type AxiomGroup } from './element-list';

function group(subjectId: string, count: number): AxiomGroup {
  return { subjectId, name: subjectId, axioms: Array.from({ length: count }, (_, index) => axiomFixture({ id: `${subjectId}-${index}`, subjectId })) };
}

const ids = (groups: ReturnType<typeof pageGroups>) => groups.map((entry) => [entry.subjectId, entry.axioms.length, entry.total]);

describe('pageGroups', () => {
  const groups = [group('a', 3), group('b', 4), group('c', 2)];

  it('cuts a page out of the groups read in order and keeps each group’s total', () => {
    expect(ids(pageGroups(groups, 0, 5))).toEqual([['a', 3, 3], ['b', 2, 4]]);
    expect(ids(pageGroups(groups, 5, 9))).toEqual([['b', 2, 4], ['c', 2, 2]]);
  });

  it('drops groups the page does not reach, also when the page starts exactly at a group boundary', () => {
    expect(ids(pageGroups(groups, 3, 7))).toEqual([['b', 4, 4]]);
    expect(ids(pageGroups(groups, 7, 9))).toEqual([['c', 2, 2]]);
  });

  it('is empty past the end', () => {
    expect(pageGroups(groups, 9, 12)).toEqual([]);
  });

  it('keeps the order of the axioms inside a group', () => {
    const [first] = pageGroups([group('a', 6)], 2, 4);
    expect(first?.axioms.map((axiom) => axiom.id)).toEqual(['a-2', 'a-3']);
  });
});

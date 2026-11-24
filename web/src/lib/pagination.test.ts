import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PAGE_SIZE, usePagination } from './pagination';

describe('usePagination', () => {
  it('slices 50 entries per page and counts the pages', () => {
    const { result } = renderHook(() => usePagination(120));
    expect(result.current).toMatchObject({ page: 1, pages: 3, start: 0, end: PAGE_SIZE });
    act(() => result.current.setPage(3));
    expect(result.current).toMatchObject({ page: 3, start: 100, end: 120 });
  });

  it('starts over at page 1 when the reset key changes, and does not bring back the old page when the key returns', () => {
    const { result, rerender } = renderHook(({ key }) => usePagination(120, key), { initialProps: { key: 'all' } });
    act(() => result.current.setPage(3));
    rerender({ key: 'property' });
    expect(result.current.page).toBe(1);
    rerender({ key: 'all' });
    expect(result.current.page).toBe(1);
  });

  it('falls back to the last page when the list shrinks', () => {
    const { result, rerender } = renderHook(({ total }) => usePagination(total), { initialProps: { total: 120 } });
    act(() => result.current.setPage(3));
    rerender({ total: 60 });
    expect(result.current).toMatchObject({ page: 2, start: 50, end: 60 });
    rerender({ total: 0 });
    expect(result.current).toMatchObject({ page: 1, pages: 1, start: 0, end: 0 });
  });
});

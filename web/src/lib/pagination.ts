import { useState } from 'react';

/** Lists longer than this are paged (ui-guidelines §9). */
export const PAGE_SIZE = 50;

export interface PageState {
  /** Current page, 1-based, never beyond the last page. */
  page: number;
  pages: number;
  /** Slice bounds of the page into the full list. */
  start: number;
  end: number;
  setPage: (page: number) => void;
}

/**
 * The page of a list of `total` entries. Pass a `resetKey` that changes with whatever filters the list:
 * the page then starts over at 1. A page past the end (the list shrank) falls back to the last page.
 */
export function usePagination(total: number, resetKey = ''): PageState {
  const [state, setState] = useState({ page: 1, key: resetKey });
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const requested = state.key === resetKey ? state.page : 1;
  const page = Math.min(Math.max(requested, 1), pages);
  return {
    page,
    pages,
    start: (page - 1) * PAGE_SIZE,
    end: Math.min(page * PAGE_SIZE, total),
    setPage: (next) => setState({ page: next, key: resetKey }),
  };
}

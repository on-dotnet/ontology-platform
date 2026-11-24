import { useCallback, useSyncExternalStore } from 'react';

function canMatchMedia(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function';
}

/** Subscribes to a CSS media query, e.g. `(min-width: 1024px)`. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!canMatchMedia()) return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => list.removeEventListener('change', onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => canMatchMedia() && window.matchMedia(query).matches,
    () => false,
  );
}

/**
 * Matches the layout breakpoint where the sidebar turns into a drawer (ui-guidelines §3). Layouts
 * that switch on it must take the switch from this query alone, not also from a Tailwind `lg:`
 * class: `lg` is in rem and moves when the user changes the browser's default font size (#8).
 */
export const DESKTOP_QUERY = '(min-width: 1024px)';

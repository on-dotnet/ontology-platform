import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

import i18n from '@/i18n';

// The first render of a route loads its code-split chunk, which can take over a second in CI containers.
configure({ asyncUtilTimeout: 3000 });

// --- jsdom gaps -------------------------------------------------------------

/** Evaluates `(min-width: Npx)` against the window width; everything else (e.g. dark mode) is false. */
function createMediaQueryList(query: string): MediaQueryList {
  const minWidth = /\(min-width:\s*(\d+)px\)/.exec(query);
  const matches = minWidth ? window.innerWidth >= Number(minWidth[1]) : false;
  return {
    matches,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  };
}

Object.defineProperty(window, 'matchMedia', { configurable: true, writable: true, value: createMediaQueryList });

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in window)) {
  Object.defineProperty(window, 'ResizeObserver', { configurable: true, writable: true, value: ResizeObserverStub });
}

if (!('scrollIntoView' in Element.prototype)) {
  Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, writable: true, value: () => undefined });
}

// Router scroll restoration calls window.scrollTo, which jsdom does not implement.
Object.defineProperty(window, 'scrollTo', { configurable: true, writable: true, value: () => undefined });

// --- per-test reset ---------------------------------------------------------

function clearCookies(): void {
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
}

beforeEach(async () => {
  window.localStorage.clear();
  clearCookies();
  document.documentElement.className = '';
  await i18n.changeLanguage('zh-CN');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

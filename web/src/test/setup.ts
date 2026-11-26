import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

import i18n from '@/i18n';

import { createMediaQueryList, resetBrowserFontSize } from './media';

// The first render of a route loads its code-split chunk, which can take over a second in CI containers.
// The Docker host is shared: the gate runs pytest next to vitest, and other worktrees or Codex tasks may
// run their own container tests at the same time, so waits of 3 s have timed out (#49). A real miss still fails.
configure({ asyncUtilTimeout: 10000 });

// --- jsdom gaps -------------------------------------------------------------

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

// CodeMirror measures text through ranges, which jsdom does not lay out.
if (!('getClientRects' in Range.prototype)) {
  const emptyRects = { length: 0, item: () => null, [Symbol.iterator]: () => [][Symbol.iterator]() };
  Object.defineProperty(Range.prototype, 'getClientRects', { configurable: true, writable: true, value: () => emptyRects });
}
if (!('getBoundingClientRect' in Range.prototype)) {
  Object.defineProperty(Range.prototype, 'getBoundingClientRect', {
    configurable: true,
    writable: true,
    value: () => ({ x: 0, y: 0, width: 0, height: 0, top: 0, right: 0, bottom: 0, left: 0, toJSON: () => ({}) }),
  });
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
  resetBrowserFontSize();
  await i18n.changeLanguage('zh-CN');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

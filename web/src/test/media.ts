/**
 * matchMedia for jsdom. `(min-width: N)` is evaluated against `window.innerWidth`; `rem` and `em`
 * use the browser's default font size, as real media queries do (page CSS does not change them).
 * Everything else (e.g. dark mode) is false.
 */

const DEFAULT_FONT_SIZE = 16;
let browserFontSize = DEFAULT_FONT_SIZE;

/** Simulates a user who changed the browser's default font size, e.g. to 20px. */
export function setBrowserFontSize(px: number): void {
  browserFontSize = px;
}

export function resetBrowserFontSize(): void {
  browserFontSize = DEFAULT_FONT_SIZE;
}

const MIN_WIDTH = /\(min-width:\s*(\d+(?:\.\d+)?)(px|rem|em)\)/;

export function createMediaQueryList(query: string): MediaQueryList {
  const minWidth = MIN_WIDTH.exec(query);
  let matches = false;
  if (minWidth) {
    const value = Number(minWidth[1]);
    const px = minWidth[2] === 'px' ? value : value * browserFontSize;
    matches = window.innerWidth >= px;
  }
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

/**
 * True while an input method (e.g. Chinese pinyin) is composing: Enter then confirms a candidate and
 * Escape cancels it, so neither may trigger the page's own shortcut. Some browsers report the key
 * that ends composition only through keyCode 229.
 */
export function isImeComposing(event: Pick<KeyboardEvent, 'isComposing' | 'keyCode'>): boolean {
  return event.isComposing || event.keyCode === 229;
}

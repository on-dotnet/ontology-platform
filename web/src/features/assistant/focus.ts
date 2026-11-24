/**
 * Markers that pass focus into the assistant panel: the shell focuses the instruction field when the
 * panel opens, and the field takes focus from the panel when it renders only after loading.
 */
const PANEL_ATTRIBUTE = 'data-assistant-panel';
const AUTOFOCUS_ATTRIBUTE = 'data-assistant-autofocus';

/** Spread onto the panel element. */
export const panelMarker = { [PANEL_ATTRIBUTE]: '' } as const;
export const PANEL_SELECTOR = `[${PANEL_ATTRIBUTE}]`;

/** Spread onto the field that receives focus when the panel opens. */
export const autofocusMarker = { [AUTOFOCUS_ATTRIBUTE]: '' } as const;
export const AUTOFOCUS_SELECTOR = `[${AUTOFOCUS_ATTRIBUTE}]`;

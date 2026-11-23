import { storage } from '@/lib/storage';

export const THEME_PREFERENCES = ['light', 'dark', 'system'] as const;
export type ThemePreference = (typeof THEME_PREFERENCES)[number];
export type ResolvedTheme = 'light' | 'dark';

/** Keep in sync with public/theme-init.js. */
export const THEME_STORAGE_KEY = 'op.theme';
export const DEFAULT_THEME: ThemePreference = 'system';

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === 'string' && (THEME_PREFERENCES as readonly string[]).includes(value);
}

export function readThemePreference(): ThemePreference {
  const saved = storage.get(THEME_STORAGE_KEY);
  return isThemePreference(saved) ? saved : DEFAULT_THEME;
}

export function writeThemePreference(preference: ThemePreference): void {
  storage.set(THEME_STORAGE_KEY, preference);
}

export function applyTheme(theme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

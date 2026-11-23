import type { i18n as I18n } from 'i18next';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';

import { DEFAULT_LOCALE } from './index';

const CODE_PATTERN = /^[a-z0-9_]+(\.[a-z0-9_]+)+$/i;

function lookup(i18n: I18n, key: string): string | undefined {
  for (const language of [i18n.resolvedLanguage ?? i18n.language, DEFAULT_LOCALE]) {
    const value: unknown = i18n.getResource(language, 'translation', key);
    if (typeof value === 'string') return value;
  }
  return undefined;
}

/**
 * Localized, user-facing text for an error: the problem `code` first, then the HTTP status,
 * then a generic message. Backend `title`/`detail` text is never shown (ui-guidelines §4).
 */
export function errorMessage(i18n: I18n, error: unknown): string {
  const keys: string[] = [];
  if (isApiError(error)) {
    if (CODE_PATTERN.test(error.code)) keys.push(`errors.${error.code}`);
    if (error.status >= 500) keys.push('errors.http.5xx');
    else if (error.status > 0) keys.push(`errors.http.${error.status}`);
  }
  for (const key of keys) {
    const text = lookup(i18n, key);
    if (text) return text;
  }
  return lookup(i18n, 'errors.unknown') ?? 'Error';
}

/** Hook form of `errorMessage`; re-renders when the language changes. */
export function useErrorMessage(): (error: unknown) => string {
  const { i18n } = useTranslation();
  return useCallback((error: unknown) => errorMessage(i18n, error), [i18n]);
}

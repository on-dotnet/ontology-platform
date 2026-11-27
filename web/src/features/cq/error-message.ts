import type { i18n } from 'i18next';

import { isApiError } from '@/api/errors';
import { errorMessage, lookupText } from '@/i18n/error-message';

export function cqMessage(locale: i18n, error: unknown) {
  const code = isApiError(error) ? error.code : typeof error === 'string' ? error : '';
  return lookupText(locale, `cq.errors.${code}`) ?? lookupText(locale, `qa.errors.${code}`) ?? errorMessage(locale, error);
}

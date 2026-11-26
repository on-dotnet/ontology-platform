import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { codeMessage, lookupText } from '@/i18n/error-message';
import { formatDateTime } from '@/lib/format';

export function QuestionError({ error, retry, disabled }: { error: unknown; retry?: () => void; disabled?: boolean }) {
  const { t, i18n } = useTranslation();
  const code = isApiError(error) ? error.code : typeof error === 'string' ? error : '';
  const key = `qa.errors.${code}`;
  let message = isApiError(error) ? codeMessage(i18n, code) : t('errors.unknown');
  if (code === 'qa.rate_limited') {
    const deadline = isApiError(error) ? error.body.retryAt : undefined;
    const date = typeof deadline === 'number' ? new Date(deadline) : undefined;
    message = date && Number.isFinite(date.getTime())
      ? t(key, { time: formatDateTime(date.toISOString(), i18n.language) })
      : t('errors.http.429');
  } else if (code && lookupText(i18n, key)) {
    message = t(key);
  }
  return <InlineNotice tone="error" title={message} action={retry && (
    <Button variant="secondary" size="sm" disabled={disabled} onClick={retry}>{t('qa.retry')}</Button>
  )} />;
}

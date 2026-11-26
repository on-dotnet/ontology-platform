import type { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { QueryResult } from '@/features/explore/query-result';
import { lookupText } from '@/i18n/error-message';

export function ReadResult<T>({ query, ...props }: ComponentProps<typeof QueryResult<T>>) {
  const { t, i18n } = useTranslation();
  const error = query.error;
  if (query.fetchStatus === 'idle' && isApiError(error)) {
    const code = error.code;
    if (code === 'metric.too_many_rows') {
      return <InlineNotice tone="error" title={t('metrics.errors.metric.too_many_rows')} />;
    }
    const refreshCatalog = code === 'query.release_changed' || code === 'metric.not_found';
    const retry = <Button variant="secondary" size="sm" onClick={
      refreshCatalog && props.onRestart ? props.onRestart : () => void query.refetch()
    }>{t('explore.retry')}</Button>;
    if (code === 'query.too_many_rows') {
      return <InlineNotice tone="error" title={t('metrics.errors.query.too_many_rows')} action={retry} />;
    }
    if (code === 'query.type_not_bound') {
      return <InlineNotice tone="error" title={t('explore.errors.type_not_bound')} action={retry} />;
    }
    if (code === 'query.release_changed') {
      return <InlineNotice tone="warning" title={t('explore.errors.release_changed')} action={retry} />;
    }
    if (code.startsWith('metric.')) {
      const title = lookupText(i18n, `metrics.errors.${code}`) ?? t('explore.errors.other');
      return <InlineNotice tone="error" title={title} action={retry} />;
    }
  }
  return <QueryResult query={query} {...props} />;
}

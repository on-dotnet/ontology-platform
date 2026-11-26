import type { UseQueryResult } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { History } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError, isForbidden } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { EmptyState } from '@/components/states/empty-state';
import { ForbiddenState } from '@/components/states/forbidden-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

function QueryLoading({ cancel, hasContent = false }: { cancel: () => void; hasContent?: boolean }) {
  const { t } = useTranslation();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 10_000);
    return () => window.clearTimeout(timer);
  }, []);
  if (hasContent && !slow) return null;
  return (
    <div className="space-y-3">
      {!hasContent && <div aria-busy="true" className="space-y-2">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
      </div>}
      <div role="status" className="flex items-center gap-3 text-sm text-muted-foreground">
        {slow ? (
          <>
            {t('explore.slow')}
            <Button size="sm" variant="secondary" onClick={cancel}>{t('explore.cancel')}</Button>
          </>
        ) : <span className="sr-only">{t('explore.loading')}</span>}
      </div>
    </div>
  );
}

const queryErrors = new Set([
  'source_unavailable', 'source_mismatch', 'timeout', 'busy', 'source_disabled',
  'invalid_filter', 'invalid_cursor', 'object_not_found', 'type_not_bound',
]);

type Query<T> = Pick<UseQueryResult<T>, 'fetchStatus' | 'data' | 'error' | 'refetch'> & {
  requestKey: string;
  cancel: () => void;
};

interface Recovery {
  id?: string;
  onRestart?: () => void;
  onFirstPage?: () => void;
}

export function ReleaseChangedNotice({ onRestart }: { onRestart: () => void }) {
  const { t } = useTranslation();
  return <InlineNotice tone="warning" title={t('explore.errors.release_changed')} action={
    <Button variant="secondary" size="sm" onClick={onRestart}>{t('explore.restart')}</Button>
  } />;
}

function QueryFailure({ error, id, retry, onRestart, onFirstPage }: Recovery & { error: Error; retry: () => void }) {
  const { t } = useTranslation();
  if (isForbidden(error)) return <ForbiddenState requiredRole="viewer" />;
  const code = isApiError(error) ? error.code : '';
  if (code === 'query.no_release' && id) {
    return (
      <EmptyState icon={History} title={t('explore.noRelease')} action={
        <Link to="/releases" search={{ ontology: id }} className={buttonVariants()}>{t('explore.publish')}</Link>
      } />
    );
  }
  if (code === 'query.release_changed') return <ReleaseChangedNotice onRestart={onRestart ?? retry} />;
  const reason = code.startsWith('query.') ? code.slice('query.'.length) : '';
  const restart = reason === 'invalid_cursor' || reason === 'type_not_bound';
  const recover = reason === 'invalid_cursor' ? onFirstPage ?? onRestart : onRestart;
  return (
    <InlineNotice tone="error" title={t(`explore.errors.${queryErrors.has(reason) ? reason : 'other'}`)}
      action={<Button variant="secondary" size="sm" onClick={restart ? recover ?? retry : retry}>
        {t(restart ? 'explore.restart' : 'explore.retry')}
      </Button>} />
  );
}

interface QueryResultProps<T> extends Recovery {
  query: Query<T>;
  keepMetadata?: boolean;
  children: (data: T) => ReactNode;
}

export function QueryResult<T>({ query, keepMetadata, children, ...recovery }: QueryResultProps<T>) {
  const { t } = useTranslation();
  const retry = () => void query.refetch();
  const fetching = query.fetchStatus === 'fetching';
  const error = query.error;
  const failure = error && <QueryFailure error={error} retry={retry} {...recovery} />;
  // A transient metadata error can be retried without dismantling the user's browsing session.
  const retain = keepMetadata && isApiError(error) && (error.status === 0 || error.status >= 500);
  if (query.data === undefined || (error && !retain)) {
    if (fetching) return <QueryLoading key={query.requestKey} cancel={query.cancel} />;
    if (failure) return failure;
    return (
      <InlineNotice tone="info" title={t(query.fetchStatus === 'paused' ? 'explore.offline' : 'explore.cancelled')}
        action={<Button variant="secondary" size="sm" onClick={retry}>{t('explore.retry')}</Button>} />
    );
  }
  return (
    <>
      {!fetching && failure}
      {children(query.data)}
      {fetching && <QueryLoading key={query.requestKey} cancel={query.cancel} hasContent />}
    </>
  );
}

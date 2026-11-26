import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Database, RefreshCw } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { EmptyState } from '@/components/states/empty-state';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { meQueryKey } from '@/features/auth/api';
import { usePermissions } from '@/features/auth/permissions';
import { SuggestBindingsDialog } from '@/features/bindings/suggest/suggest-bindings-dialog';
import { codeMessage, useErrorMessage } from '@/i18n/error-message';

import { rememberSource, sourceKey, type DataSource } from './api';
import { CatalogBrowser, catalogKey } from './catalog-browser';

interface CatalogPanelProps {
  source: DataSource;
  canBrowse: boolean;
  onEdit?: (repairPassword: boolean) => void;
}

function ReadingCatalog({ hasSnapshot }: { hasSnapshot: boolean }) {
  const { t } = useTranslation();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timeout = window.setTimeout(() => setSlow(true), 10_000);
    return () => window.clearTimeout(timeout);
  }, []);
  return (
    <div className="space-y-3">
      {!hasSnapshot && (
        <div aria-busy="true" className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32 md:col-span-2" />
          </div>
        </div>
      )}
      <span role="status" aria-live="polite" className={hasSnapshot || slow ? 'text-sm text-muted-foreground' : 'sr-only'}>
        {t(slow ? 'datasources.catalog.stillReading' : 'datasources.catalog.loading')}
      </span>
    </div>
  );
}

function SourceCatalog({ source, canBrowse, onEdit }: CatalogPanelProps) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const message = useErrorMessage();
  const client = useQueryClient();
  const { id, catalog } = source;
  const [denied, setDenied] = useState(false);
  const { canEditBindings } = usePermissions();
  const [suggestOpen, setSuggestOpen] = useState(false);
  const allowed = !denied && canBrowse && catalog !== null;
  const needsCatalogInfo = !denied && canBrowse && catalog === null;
  useEffect(() => {
    // Regranting the role can leave the viewer's redacted detail in the cache.
    if (needsCatalogInfo) void client.invalidateQueries({ queryKey: sourceKey(id), exact: true });
  }, [client, id, needsCatalogInfo]);
  const unwrapCatalog: typeof unwrap = async (request) => {
    try {
      return await unwrap(request);
    } catch (error) {
      if (isApiError(error) && error.status === 403 && error.code !== 'auth.csrf_failed') {
        // A later page can revoke access to rows already visible from an earlier successful request.
        setDenied(true);
        client.removeQueries({ queryKey: catalogKey(id) });
        void client.invalidateQueries({ queryKey: meQueryKey, exact: true });
        void client.invalidateQueries({ queryKey: sourceKey(id), exact: true });
      }
      throw error;
    }
  };
  const canRefresh = allowed && source.status === 'active';
  const refresh = useMutation({
    mutationFn: () => unwrapCatalog(api.POST('/api/data-sources/{id}/catalog/refresh', { params: { path: { id } } })),
    onSuccess: (updated) => rememberSource(client, updated),
  });
  const postFailed = refresh.isError && canRefresh;
  const catalogFailed = canRefresh && catalog.status === 'failed';
  const refreshedAt = allowed ? catalog.refreshedAt : null;
  if (allowed && source.status === 'archived' && !refreshedAt) return null;
  const postCode = isApiError(refresh.error) ? refresh.error.code : null;
  const errorCode = postFailed ? postCode : catalog?.errorCode;
  const tooLarge = errorCode === 'catalog.too_large';
  const repairPassword = errorCode === 'datasource.credential_unreadable';
  const refreshButton = (primary = false) => (
    <Button variant={primary ? 'primary' : 'secondary'} loading={refresh.isPending} onClick={() => refresh.mutate()}>
      <RefreshCw aria-hidden />{t('datasources.catalog.refresh')}
    </Button>
  );

  return (
    <section aria-labelledby={titleId}>
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-4">
          <div>
            <CardTitle id={titleId}>{t('datasources.catalog.title')}</CardTitle>
            {refreshedAt && (
              <dl className="flex flex-wrap gap-x-2 text-sm text-muted-foreground">
                <dt>{t('datasources.catalog.lastRead')}</dt>
                <dd><RelativeTime value={refreshedAt} /></dd>
              </dl>
            )}
          </div>
          {canRefresh && catalog.status === 'ready' && !postFailed && (
            <div className="flex flex-wrap gap-2">
              {refreshButton()}
              {canEditBindings && (
                <Button aria-haspopup="dialog" onClick={() => setSuggestOpen(true)}>{t('bindings.suggest.title')}</Button>
              )}
            </div>
          )}
          {/* Outside the condition: a refresh started elsewhere must not close a running suggestion. */}
          {canEditBindings && suggestOpen && (
            <SuggestBindingsDialog open onOpenChange={setSuggestOpen} dataSourceId={id} />
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {!allowed ? (
            <p className="text-sm text-muted-foreground">{t('datasources.catalog.forbidden')}</p>
          ) : (
            <>
              {(postFailed || catalogFailed) && (
                <InlineNotice
                  tone={tooLarge ? 'warning' : 'error'}
                  announce={postFailed}
                  action={canRefresh && (
                    <div className="flex flex-wrap gap-2">
                      {onEdit && (tooLarge || repairPassword) && (
                        <Button size="sm" variant="secondary" onClick={() => onEdit(repairPassword)}>{t('datasources.catalog.edit')}</Button>
                      )}
                      <Button size="sm" variant="secondary" loading={refresh.isPending} onClick={() => refresh.mutate()}>
                        {t('datasources.catalog.retry')}
                      </Button>
                    </div>
                  )}
                >
                  {postFailed ? message(refresh.error) : codeMessage(i18n, errorCode)}
                </InlineNotice>
              )}
              {canRefresh && catalog.status === 'never' && !postFailed && (
                <EmptyState
                  icon={Database}
                  title={t('datasources.catalog.never')}
                  headingLevel="h3"
                  action={refreshButton(true)}
                />
              )}
              {canRefresh && catalog.status === 'refreshing' && <ReadingCatalog hasSnapshot={Boolean(refreshedAt)} />}
              {refreshedAt && (
                <CatalogBrowser key={refreshedAt} id={id} refreshedAt={refreshedAt} unwrapCatalog={unwrapCatalog} />
              )}
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

export function CatalogPanel(props: CatalogPanelProps) {
  return <SourceCatalog key={`${props.source.id}:${props.canBrowse ? 'editor' : 'viewer'}`} {...props} />;
}

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Cable } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import { isApiError } from '@/api/errors';
import { WarnTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardTitle } from '@/components/ui/card';
import { RelativeTime } from '@/components/ui/relative-time';
import { codeMessage, useErrorMessage } from '@/i18n/error-message';

import { listKey, sourceKey, type DataSource } from './api';
import { ConnectionTestResult } from './connection-test-result';

type ConnectionCardProps = { source: DataSource; onRepairPassword?: () => void };

export function ConnectionCard(props: ConnectionCardProps) {
  const { source } = props;
  // A result for the previous credentials or endpoint must disappear as soon as the settings change.
  const settings = JSON.stringify([source.status, source.connection, source.credentialUpdatedAt, source.hasCredential]);
  return <ConnectionDetails key={settings} {...props} />;
}

function ConnectionDetails({ source, onRepairPassword }: ConnectionCardProps) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const message = useErrorMessage();
  const historyId = useId();
  const feedbackId = useId();
  const key = sourceKey(source.id);
  const { lastTest } = source;
  const at = lastTest?.at;
  function refreshSource() {
    return Promise.all([
      client.invalidateQueries({ queryKey: key, exact: true }),
      client.invalidateQueries({ queryKey: listKey }),
    ]);
  }
  const test = useMutation({
    mutationFn: async () => {
      const result = await unwrap(api.POST('/api/data-sources/{id}/test', { params: { path: { id: source.id } } }));
      await refreshSource();
      return { result, observedAt: client.getQueryData<DataSource>(key)?.lastTest?.at };
    },
    onError: refreshSource,
  });
  const { connection } = source;
  if (!connection) return null;
  const details = [
    ['host', connection.host],
    ['port', connection.port],
    ['database', connection.database],
    ['username', connection.username],
    ['ssl', t(`datasources.ssl.${connection.sslMode}`)],
    ['schemas', connection.schemas.length ? new Intl.ListFormat(i18n.language).format(connection.schemas) : t('datasources.connection.allSchemas')],
    ['password', t(source.hasCredential ? 'datasources.connection.stored' : 'datasources.connection.missing')],
    ['credentialAt', source.credentialUpdatedAt ? <RelativeTime value={source.credentialUpdatedAt} /> : t('datasources.unavailable')],
  ] as const;
  // The POST has no timestamp. Only the saved result can be paired with the time of a recorded test.
  const local = test.data?.observedAt === at ? test.data?.result : null;
  const repair = onRepairPassword && (
    <Button size="sm" variant="secondary" onClick={onRepairPassword}>{t('datasources.connection.reenter')}</Button>
  );
  const feedbackCode = isApiError(test.error) ? test.error.code : local?.code;
  const repairFeedback = feedbackCode === 'datasource.credential_unreadable' ? repair : undefined;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-5">
        <CardTitle>{t('datasources.connection.title')}</CardTitle>
        {source.status === 'active' && (
          <Button variant="secondary" size="sm" loading={test.isPending} onClick={() => test.mutate()}>
            <Cable aria-hidden />{t('datasources.test.action')}
          </Button>
        )}
      </div>
      <CardContent className="space-y-5">
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-4">
          {details.map(([field, value]) => (
            <div key={field} className="min-w-0">
              <dt className="text-xs font-medium text-muted-foreground">{t(`datasources.fields.${field}`)}</dt>
              <dd className="mt-1 break-words text-sm">{value}</dd>
            </div>
          ))}
        </dl>
        <section aria-labelledby={historyId} className="space-y-2 border-t border-border pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={historyId} className="text-sm font-semibold">{t('datasources.connection.lastTest')}</h3>
            {lastTest ? (
              <>
                <Badge tone={lastTest.ok ? 'success' : 'error'}>{t(lastTest.ok ? 'datasources.status.ok' : 'datasources.status.failed')}</Badge>
                <RelativeTime value={lastTest.at} className="text-xs text-muted-foreground" />
                {lastTest.warnings.includes('account_can_write') && <WarnTip>{t('datasources.test.writeWarning')}</WarnTip>}
              </>
            ) : <span className="text-sm text-muted-foreground">{t('datasources.status.untested')}</span>}
          </div>
          {lastTest && !lastTest.ok && (
            <InlineNotice tone="error" announce={false} action={lastTest.code === 'datasource.credential_unreadable' && !repairFeedback ? repair : undefined}>
              {codeMessage(i18n, lastTest.code, 'errors.datasource.connect_failed')}
            </InlineNotice>
          )}
        </section>
        {(test.isError || local) && (
          <section aria-labelledby={feedbackId} className="space-y-2">
            <h3 id={feedbackId} className="text-sm font-semibold">{t('datasources.test.current')}</h3>
            {test.isError ? <InlineNotice tone="error" action={repairFeedback}>{message(test.error)}</InlineNotice>
              : local && <ConnectionTestResult result={local} action={repairFeedback} />}
          </section>
        )}
      </CardContent>
    </Card>
  );
}

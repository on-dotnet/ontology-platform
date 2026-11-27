import { useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useRouterState } from '@tanstack/react-router';
import { Database, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Pagination } from '@/components/ui/pagination';
import { RelativeTime } from '@/components/ui/relative-time';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePermissions } from '@/features/auth/permissions';
import { SuggestBindingsDialog } from '@/features/bindings/suggest/suggest-bindings-dialog';
import { useErrorMessage } from '@/i18n/error-message';
import { usePagination } from '@/lib/pagination';

import { rememberSource, testSavedSource, useSourceList, type DataSource } from './api';
import { DataSourceDialog } from './data-source-dialog';
import { SourceStatus } from './source-status';

export function DataSourcesPage() {
  const { t } = useTranslation();
  const query = useSourceList();
  const { canManageDataSources, canBrowseCatalog, canEditBindings } = usePermissions();
  const search = useRouterState({ select: (state) => state.location.searchStr });
  const params = new URLSearchParams(search);
  const ontologyId = params.get('ontologyId')?.trim();
  const typeIds = params.get('typeIds')?.split(',').map((id) => id.trim()).filter(Boolean) ?? [];
  const [creating, setCreating] = useState(false);
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const message = useErrorMessage();

  const create = canManageDataSources && (
    <Button onClick={() => setCreating(true)}><Plus aria-hidden />{t('datasources.create')}</Button>
  );
  return (
    <>
      <PageHeader title={t('datasources.title')} info={t('datasources.form.description')} actions={query.data?.length === 0 ? null : create} />
      <QueryState query={query}>
        {(sources) => sources.length ? <SourceTable sources={sources} canBrowse={canBrowseCatalog} /> : (
          <Card>
            <EmptyState icon={Database} tone="success"
              title={t(canManageDataSources ? 'datasources.list.empty' : 'datasources.list.askAdmin')}
              action={create}
            />
          </Card>
        )}
      </QueryState>
      {canEditBindings && ontologyId && typeIds.length > 0 && (
        <SuggestBindingsDialog key={[ontologyId, ...typeIds].join(',')} open ontologyId={ontologyId} typeIds={typeIds}
          onOpenChange={(open) => {
            if (open) return;
            params.delete('ontologyId');
            params.delete('typeIds');
            void navigate({ href: params.size ? `/data?${params}` : '/data', replace: true });
          }} />
      )}
      {creating && canManageDataSources && (
        <DataSourceDialog onClose={() => setCreating(false)} onSaved={async (source, testAfterCreate) => {
          if (testAfterCreate) {
            try {
              await testSavedSource(client, source.id);
            } catch (error) {
              toast.error(t('datasources.test.action'), message(error));
            }
          } else {
            await rememberSource(client, source);
          }
          setCreating(false);
          toast.success(t('datasources.saved'));
          await navigate({ to: '/data/$dataSourceId', params: { dataSourceId: source.id } });
        }} />
      )}
    </>
  );
}

function SourceTable({ sources, canBrowse }: { sources: DataSource[]; canBrowse: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const pagination = usePagination(sources.length);
  return (
    <Card className="min-w-0 overflow-x-auto">
      <Table aria-label={t('datasources.title')}>
        <TableHeader>
          <TableRow>
            <TableHead>{t('datasources.fields.name')}</TableHead>
            <TableHead>{t('datasources.fields.kind')}</TableHead>
            <TableHead>{t('datasources.list.status')}</TableHead>
            {canBrowse && <TableHead>{t('datasources.fields.host')}</TableHead>}
            {canBrowse && <TableHead>{t('datasources.fields.database')}</TableHead>}
            <TableHead>{t('datasources.list.catalogAt')}</TableHead>
            <TableHead numeric>{t('datasources.list.count')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.slice(pagination.start, pagination.end).map((source) => {
            const target = { to: '/data/$dataSourceId', params: { dataSourceId: source.id } } as const;
            return (
              <TableRow key={source.id} className="cursor-pointer" onClick={(event) => {
                if (event.target instanceof Element && !event.target.closest('a')) void navigate(target);
              }}>
                <TableCell>
                  <Link {...target} className="break-words rounded font-medium text-primary-strong hover:underline">
                    {source.name}
                  </Link>
                </TableCell>
                <TableCell>{t(`datasources.kind.${source.kind}`)}</TableCell>
                <TableCell><SourceStatus source={source} /></TableCell>
                {canBrowse && <TableCell>{source.connection?.host ?? t('datasources.unavailable')}</TableCell>}
                {canBrowse && <TableCell>{source.connection?.database ?? t('datasources.unavailable')}</TableCell>}
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {canBrowse && source.catalog?.refreshedAt
                    ? <RelativeTime value={source.catalog.refreshedAt} />
                    : t('datasources.unavailable')}
                </TableCell>
                <TableCell numeric>{source.boundTypeCount ?? t('datasources.unknown')}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <Pagination state={pagination} total={sources.length} />
    </Card>
  );
}

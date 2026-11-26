import { useQueryClient } from '@tanstack/react-query';
import { Archive, Ellipsis, Pencil } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { LoadingState } from '@/components/states/loading-state';
import { QueryState } from '@/components/states/query-state';
import { buttonVariants } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { usePermissions } from '@/features/auth/permissions';

import { rememberSource, useSource, type DataSource } from './api';
import { ArchiveDialog } from './archive-dialog';
import { CatalogPanel } from './catalog-panel';
import { ConnectionCard } from './connection-card';
import { DataSourceDialog } from './data-source-dialog';
import { SourceStatus } from './source-status';

export function DataSourceDetailPage({ dataSourceId }: { dataSourceId: string }) {
  const { t } = useTranslation();
  const { canManageDataSources, canBrowseCatalog } = usePermissions();
  const query = useSource(dataSourceId, canBrowseCatalog);
  return (
    <>
      {!query.isSuccess && <PageHeader title={t('datasources.title')} />}
      <QueryState query={query} loading={<LoadingState variant="detail" />}>
        {(source) => <SourceDetail source={source} canManage={canManageDataSources} canBrowse={canBrowseCatalog} />}
      </QueryState>
    </>
  );
}

function SourceDetail({ source, canManage, canBrowse }: { source: DataSource; canManage: boolean; canBrowse: boolean }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<'edit' | 'repair' | 'archive' | null>(null);
  const active = source.status === 'active';
  const editable = active && canManage && source.connection !== null;
  async function saved(updated: DataSource) {
    await rememberSource(client, updated);
    setDialog(null);
    toast.success(t(updated.status === 'archived' ? 'datasources.archive.done' : 'datasources.saved'));
  }
  return (
    <>
      <PageHeader title={source.name} actions={
        <>
          <SourceStatus source={source} />
          {canManage && active && (
            <DropdownMenu>
              <DropdownMenuTrigger aria-label={t('datasources.more')} title={t('datasources.more')}
                className={buttonVariants({ variant: 'secondary', size: 'icon-sm' })}>
                <Ellipsis aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {editable && <DropdownMenuItem onClick={() => setDialog('edit')}><Pencil aria-hidden />{t('datasources.edit')}</DropdownMenuItem>}
                <DropdownMenuItem onClick={() => setDialog('archive')}><Archive aria-hidden />{t('datasources.archive.action')}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </>
      } />
      <div className="space-y-6">
        {canBrowse && source.connection && (
          <ConnectionCard source={source} onRepairPassword={editable ? () => setDialog('repair') : undefined} />
        )}
        <CatalogPanel source={source} canBrowse={canBrowse}
          onEdit={editable ? (repairPassword) => setDialog(repairPassword ? 'repair' : 'edit') : undefined} />
      </div>
      {editable && (dialog === 'edit' || dialog === 'repair') && (
        <DataSourceDialog source={source} repairPassword={dialog === 'repair'} onSaved={saved} onClose={() => setDialog(null)} />
      )}
      {active && canManage && dialog === 'archive' && <ArchiveDialog source={source} onArchived={saved} onClose={() => setDialog(null)} />}
    </>
  );
}

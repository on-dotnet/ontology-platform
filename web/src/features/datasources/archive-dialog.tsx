import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useErrorMessage } from '@/i18n/error-message';

import type { DataSource } from './api';

export function ArchiveDialog({ source, onClose, onArchived }: {
  source: DataSource;
  onClose: () => void;
  onArchived: (source: DataSource) => Promise<void>;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const archive = useMutation({
    mutationFn: () => unwrap(api.POST('/api/data-sources/{id}/archive', { params: { path: { id: source.id } } })),
    onSuccess: onArchived,
  });
  const inUse = isApiError(archive.error) && archive.error.code === 'datasource.in_use';
  const reportedCount = isApiError(archive.error) ? archive.error.body.boundTypeCount : undefined;
  const count = typeof reportedCount === 'number' ? reportedCount : source.boundTypeCount;
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !archive.isPending) onClose(); }}>
      <DialogContent closeLabel={t('datasources.close')}>
        <DialogTitle>{t('datasources.archive.title', { name: source.name })}</DialogTitle>
        <DialogDescription>{t('datasources.archive.consequences')}</DialogDescription>
        {archive.isError && (
          <InlineNotice tone="error" className="mt-4">
            {message(archive.error)}
            {inUse && count !== null && <p>{t('datasources.archive.count', { count })}</p>}
          </InlineNotice>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" disabled={archive.isPending} onClick={onClose}>{t('datasources.cancel')}</Button>
          <Button variant="destructive" loading={archive.isPending} onClick={() => archive.mutate()}>
            {t('datasources.archive.confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

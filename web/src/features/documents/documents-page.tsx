import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, FileText, RefreshCw, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { LoadingState } from '@/components/states/loading-state';
import { QueryState } from '@/components/states/query-state';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { RelativeTime } from '@/components/ui/relative-time';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { AiStatusNotice } from '@/features/ai/ai-status';
import { usePermissions } from '@/features/auth/permissions';
import type { OntologySummary } from '@/features/ontologies/api';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { codeMessage, lookupText, useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';
import { formatBytes } from '@/lib/format';

import { documentKeys, retryDocument, useDocuments, type DocumentInfo } from './api';
import { DocumentProgress } from './document-progress';
import { UploadDropZone, UploadProblems, useDocumentUpload, useFileDrop, useFilePicker } from './upload';

interface DocumentsPageProps {
  ontologyId: string | undefined;
  onOntologyChange: (id: string) => void;
}

export function DocumentsPage({ ontologyId, onOntologyChange }: DocumentsPageProps) {
  const { t } = useTranslation();
  const { canUpload } = usePermissions();
  const { query, ontologies, selected } = useSelectedOntology(ontologyId);
  const upload = useDocumentUpload({
    ontologyId: selected?.id,
    needsOntology: ontologies?.length === 0,
    onUploaded: (target) => {
      if (target !== selected?.id) onOntologyChange(target);
    },
  });
  const picker = useFilePicker(upload.submit);

  return (
    <>
      <PageHeader
        title={t('nav.documents')}
        info={t('pages.documents.info')}
        actions={
          <>
            {selected && ontologies ? (
              <OntologySelector ontologies={ontologies} value={selected.id} onValueChange={onOntologyChange} />
            ) : null}
            {canUpload && ontologies ? (
              <Button onClick={picker.open} loading={upload.isUploading}>
                {upload.isUploading ? null : <Upload aria-hidden />}
                {upload.isUploading ? t('upload.uploading') : t('documents.upload')}
              </Button>
            ) : null}
          </>
        }
      />
      {picker.input}
      {upload.dialog}

      <div className="space-y-4">
        <AiStatusNotice />
        <UploadProblems problems={upload.problems} onDismiss={upload.dismissProblems} />
        <QueryState query={query} loading={<LoadingState />}>
          {(list) =>
            list.length === 0 || !selected ? (
              <Card>
                {canUpload ? (
                  <div className="p-6">
                    <UploadDropZone
                      onFiles={upload.submit}
                      busy={upload.isUploading}
                      title={t('documents.noOntologyUploadTitle')}
                      className="py-12"
                    />
                  </div>
                ) : (
                  <EmptyState icon={FileText} title={t('documents.noOntologyTitle')} description={t('documents.noOntologyDescription')} />
                )}
              </Card>
            ) : (
              <DocumentsTable ontology={selected} canUpload={canUpload} busy={upload.isUploading} onFiles={upload.submit} />
            )
          }
        </QueryState>
      </div>
    </>
  );
}

interface DocumentsTableProps {
  ontology: OntologySummary;
  canUpload: boolean;
  busy: boolean;
  onFiles: (files: File[]) => void;
}

function DocumentsTable({ ontology, canUpload, busy, onFiles }: DocumentsTableProps) {
  const { t, i18n } = useTranslation();
  const query = useDocuments(ontology.id);
  const { dragging, handlers } = useFileDrop(onFiles, canUpload && !busy);

  return (
    <QueryState query={query}>
      {(data) => {
        const documents = data.pages.flatMap((page) => page.items);
        if (documents.length === 0) {
          return (
            <Card>
              {canUpload ? (
                <div className="p-6">
                  <UploadDropZone onFiles={onFiles} busy={busy} title={t('documents.emptyUploadTitle')} className="py-12" />
                </div>
              ) : (
                <EmptyState icon={FileText} title={t('documents.emptyTitle')} description={t('documents.emptyDescription')} />
              )}
            </Card>
          );
        }
        return (
          <Card
            {...handlers}
            data-dragging={dragging || undefined}
            className={cn('transition-shadow data-[dragging]:ring-2 data-[dragging]:ring-primary')}
          >
            <Table aria-label={t('documents.tableLabel')}>
              <TableHeader>
                <TableRow className="border-t-0 hover:bg-transparent">
                  <TableHead>{t('documents.columns.name')}</TableHead>
                  <TableHead>{t('documents.columns.status')}</TableHead>
                  <TableHead>{t('documents.columns.uploadedAt')}</TableHead>
                  <TableHead>{t('documents.columns.result')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((document) => (
                  <TableRow key={document.id}>
                    <TableCell className="max-w-80">
                      <p className="truncate font-medium text-foreground" title={document.filename}>
                        {document.filename}
                      </p>
                      <p className="text-xs text-muted-foreground tabular-nums">
                        {formatBytes(document.sizeBytes, i18n.resolvedLanguage ?? i18n.language)}
                        {document.pageCount ? ` · ${t('documents.pages', { count: document.pageCount })}` : ''}
                      </p>
                    </TableCell>
                    <TableCell>
                      <DocumentProgress document={document} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      <RelativeTime value={document.createdAt} />
                    </TableCell>
                    <TableCell>
                      <DocumentResult document={document} canRetry={canUpload} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {query.hasNextPage ? (
              <div className="flex justify-center border-t border-border p-3">
                <Button variant="ghost" size="sm" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                  {t('documents.loadMore')}
                </Button>
              </div>
            ) : null}
          </Card>
        );
      }}
    </QueryState>
  );
}

function DocumentResult({ document, canRetry }: { document: DocumentInfo; canRetry: boolean }) {
  const { t, i18n } = useTranslation();
  const message = useErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: () => retryDocument(document.id),
    onSuccess: async () => {
      toast.success(t('documents.retryStarted'));
      await queryClient.invalidateQueries({ queryKey: documentKeys.list(document.ontologyId) });
    },
    onError: (error) => toast.error(t('documents.retryFailed'), message(error)),
  });

  if (document.status === 'failed') {
    return (
      <div className="flex max-w-80 flex-col items-start gap-1.5">
        <p className="text-sm text-error-strong">
          {(document.errorCode ? lookupText(i18n, `documents.failures.${document.errorCode}`) : undefined) ??
            codeMessage(i18n, document.errorCode, 'documents.failedUnknown')}
        </p>
        {canRetry ? (
          <Button variant="secondary" size="sm" loading={retry.isPending} onClick={() => retry.mutate()}>
            {retry.isPending ? null : <RefreshCw aria-hidden />}
            {t('common.retry')}
          </Button>
        ) : null}
      </div>
    );
  }
  if (document.status !== 'ready') return <span className="text-muted-foreground">{t('documents.resultPending')}</span>;
  if (!document.changeSetId) return <span className="text-muted-foreground">{t('documents.resultNothingNew')}</span>;
  return (
    <Link
      to="/review/$changeSetId"
      params={{ changeSetId: document.changeSetId }}
      className="inline-flex items-center gap-1 rounded font-medium text-primary-strong hover:underline"
    >
      {t('documents.viewChangeSet')}
      <ArrowRight className="size-3.5" aria-hidden />
    </Link>
  );
}

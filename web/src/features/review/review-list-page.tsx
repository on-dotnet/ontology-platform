import { Link } from '@tanstack/react-router';
import { ClipboardCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePermissions } from '@/features/auth/permissions';
import { useDocument } from '@/features/documents/api';
import type { OntologySummary } from '@/features/ontologies/api';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';

import { useChangeSets, type ChangeSetSummary } from './api';

interface ReviewListPageProps {
  ontologyId: string | undefined;
  onOntologyChange: (id: string) => void;
}

export function ReviewListPage({ ontologyId, onOntologyChange }: ReviewListPageProps) {
  const { t } = useTranslation();
  const { canUpload } = usePermissions();
  const { query, ontologies, selected } = useSelectedOntology(ontologyId);

  return (
    <>
      <PageHeader
        title={t('nav.review')}
        info={t('pages.review.info')}
        actions={
          selected && ontologies ? <OntologySelector ontologies={ontologies} value={selected.id} onValueChange={onOntologyChange} /> : null
        }
      />
      <QueryState query={query}>
        {(list) =>
          list.length === 0 || !selected ? (
            <Card>
              <EmptyState
                icon={ClipboardCheck}
                tone="warning"
                title={t('review.noOntologyTitle')}
                description={t('review.noOntologyDescription')}
                action={
                  canUpload ? (
                    <Link to="/documents" className={buttonVariants({ variant: 'primary' })}>
                      {t('documents.upload')}
                    </Link>
                  ) : undefined
                }
              />
            </Card>
          ) : (
            <ChangeSetTable ontology={selected} canUpload={canUpload} />
          )
        }
      </QueryState>
    </>
  );
}

const statusTone: Record<ChangeSetSummary['status'], BadgeTone> = { open: 'warning', merged: 'success', rejected: 'neutral' };

function ChangeSetTable({ ontology, canUpload }: { ontology: OntologySummary; canUpload: boolean }) {
  const { t } = useTranslation();
  const query = useChangeSets(ontology.id);
  return (
    <QueryState query={query}>
      {(changeSets) =>
        changeSets.length === 0 ? (
          <Card>
            <EmptyState
              icon={ClipboardCheck}
              tone="warning"
              title={t('review.emptyTitle')}
              description={t('review.emptyDescription')}
              action={
                canUpload ? (
                  <Link to="/documents" search={{ ontology: ontology.id }} className={buttonVariants({ variant: 'primary' })}>
                    {t('documents.upload')}
                  </Link>
                ) : undefined
              }
            />
          </Card>
        ) : (
          <Card>
            <Table aria-label={t('review.tableLabel')}>
              <TableHeader>
                <TableRow className="border-t-0 hover:bg-transparent">
                  <TableHead>{t('review.columns.title')}</TableHead>
                  <TableHead>{t('review.columns.source')}</TableHead>
                  <TableHead numeric>{t('review.columns.pending')}</TableHead>
                  <TableHead numeric>{t('review.columns.accepted')}</TableHead>
                  <TableHead numeric>{t('review.columns.rejected')}</TableHead>
                  <TableHead>{t('review.columns.status')}</TableHead>
                  <TableHead>{t('review.columns.createdAt')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {changeSets.map((changeSet) => (
                  <TableRow key={changeSet.id}>
                    <TableCell className="max-w-96">
                      <Link
                        to="/review/$changeSetId"
                        params={{ changeSetId: changeSet.id }}
                        className="block truncate rounded font-medium text-primary-strong hover:underline"
                      >
                        {changeSet.title}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-64 text-muted-foreground">
                      <DocumentName id={changeSet.documentId} />
                    </TableCell>
                    <TableCell numeric className="font-semibold text-warning-strong">
                      {changeSet.counts.pending}
                    </TableCell>
                    <TableCell numeric>{changeSet.counts.accepted}</TableCell>
                    <TableCell numeric>{changeSet.counts.rejected}</TableCell>
                    <TableCell>
                      <Badge tone={statusTone[changeSet.status]}>{t(`review.status.${changeSet.status}`)}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      <RelativeTime value={changeSet.createdAt} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )
      }
    </QueryState>
  );
}

/** Filename of a change set's source document. */
export function DocumentName({ id }: { id: string | null }) {
  const { t } = useTranslation();
  const query = useDocument(id);
  if (!id) return <span>{t('review.noSource')}</span>;
  if (query.isPending) return <Skeleton className="h-4 w-32" />;
  if (!query.data) return <span>{t('evidence.unknownDocument')}</span>;
  return (
    <span className="block truncate" title={query.data.filename}>
      {query.data.filename}
    </span>
  );
}

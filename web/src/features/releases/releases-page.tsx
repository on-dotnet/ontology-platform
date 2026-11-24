import { useMutation } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { CircleCheck, Download, History, Rocket } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { RelativeTime } from '@/components/ui/relative-time';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { usePermissions } from '@/features/auth/permissions';
import type { OntologySummary } from '@/features/ontologies/api';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { useErrorMessage } from '@/i18n/error-message';
import { downloadText } from '@/lib/download';

import { exportReleaseTurtle, useReleases, type ReleaseSummary } from './api';
import { CompareCard } from './compare';
import { ActivateReleaseDialog, PublishReleaseDialog } from './release-dialogs';

interface ReleasesPageProps {
  ontologyId: string | undefined;
  onOntologyChange: (id: string) => void;
}

export function ReleasesPage({ ontologyId, onOntologyChange }: ReleasesPageProps) {
  const { t } = useTranslation();
  const { canReview } = usePermissions();
  const { query, ontologies, selected } = useSelectedOntology(ontologyId);
  const [publishing, setPublishing] = useState(false);

  return (
    <>
      <PageHeader
        title={t('nav.releases')}
        info={t('pages.releases.info')}
        actions={
          selected && ontologies ? (
            <>
              <OntologySelector ontologies={ontologies} value={selected.id} onValueChange={onOntologyChange} />
              {canReview ? (
                <Button onClick={() => setPublishing(true)}>
                  <Rocket aria-hidden />
                  {t('releases.publishNew')}
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <QueryState query={query}>
        {(list) =>
          list.length === 0 || !selected ? (
            <Card>
              <EmptyState icon={History} title={t('releases.noOntologyTitle')} description={t('releases.noOntologyDescription')} />
            </Card>
          ) : (
            <ReleasesTable ontology={selected} canReview={canReview} />
          )
        }
      </QueryState>
      {selected && canReview ? <PublishReleaseDialog ontology={selected} open={publishing} onOpenChange={setPublishing} /> : null}
    </>
  );
}

function ReleasesTable({ ontology, canReview }: { ontology: OntologySummary; canReview: boolean }) {
  const { t } = useTranslation();
  const toast = useToast();
  const message = useErrorMessage();
  const query = useReleases(ontology.id);
  const [activating, setActivating] = useState<ReleaseSummary | null>(null);

  const exportTurtle = useMutation({
    mutationFn: (release: ReleaseSummary) => exportReleaseTurtle(release.id).then((text) => ({ release, text })),
    onSuccess: ({ release, text }) => {
      downloadText(`${ontology.key}-v${release.version}.ttl`, text);
      toast.success(t('releases.exported', { version: release.version }));
    },
    onError: (error) => toast.error(t('releases.exportFailed'), message(error)),
  });

  return (
    <QueryState query={query}>
      {(releases) => {
        const current = releases.find((release) => release.isActive);
        if (releases.length === 0) {
          return (
            <Card>
              <EmptyState
                icon={History}
                title={t('releases.emptyTitle')}
                description={canReview ? t('releases.emptyDescriptionReviewer') : t('releases.emptyDescription')}
                action={
                  ontology.entityTypeCount === 0 ? (
                    <Link to="/ontology" search={{ ontology: ontology.id }} className={buttonVariants({ variant: 'secondary' })}>
                      {t('releases.viewOntology')}
                    </Link>
                  ) : undefined
                }
              />
            </Card>
          );
        }
        return (
          <div className="space-y-6">
            <Card>
              <Table aria-label={t('releases.tableLabel')}>
                <TableHeader>
                  <TableRow className="border-t-0 hover:bg-transparent">
                    <TableHead>{t('releases.columns.version')}</TableHead>
                    <TableHead>{t('releases.columns.title')}</TableHead>
                    <TableHead numeric>{t('releases.columns.elements')}</TableHead>
                    <TableHead>{t('releases.columns.publishedAt')}</TableHead>
                    <TableHead>{t('releases.columns.current')}</TableHead>
                    <TableHead className="text-right">{t('releases.columns.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {releases.map((release) => {
                    const exporting = exportTurtle.isPending && exportTurtle.variables?.id === release.id;
                    const exportLabel = t('releases.exportVersion', { version: release.version });
                    return (
                      <TableRow key={release.id}>
                        <TableCell className="whitespace-nowrap font-semibold tabular-nums text-foreground">
                          {t('releases.versionLabel', { version: release.version })}
                        </TableCell>
                        <TableCell className="max-w-96">
                          <p className="truncate font-medium text-foreground">{release.title}</p>
                          {release.notes ? <p className="line-clamp-1 text-xs text-muted-foreground">{release.notes}</p> : null}
                        </TableCell>
                        <TableCell numeric>{release.elementCount}</TableCell>
                        <TableCell className="whitespace-nowrap text-muted-foreground">
                          <RelativeTime value={release.createdAt} />
                        </TableCell>
                        <TableCell>
                          {release.isActive ? (
                            <Badge tone="success">
                              <CircleCheck aria-hidden />
                              {t('releases.current')}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">
                              <span aria-hidden>—</span>
                              <span className="sr-only">{t('releases.notCurrent')}</span>
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            <Tooltip content={exportLabel}>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                aria-label={exportLabel}
                                loading={exporting}
                                onClick={() => exportTurtle.mutate(release)}
                              >
                                {exporting ? null : <Download aria-hidden />}
                              </Button>
                            </Tooltip>
                            {canReview && !release.isActive ? (
                              <Button variant="secondary" size="sm" onClick={() => setActivating(release)}>
                                {t('releases.activate.action')}
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {canReview ? (
                <ActivateReleaseDialog ontology={ontology} release={activating} current={current} onClose={() => setActivating(null)} />
              ) : null}
            </Card>
            <CompareCard ontology={ontology} releases={releases} />
          </div>
        );
      }}
    </QueryState>
  );
}

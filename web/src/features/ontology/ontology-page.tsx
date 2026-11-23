import { useMutation } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Download, List, Network, Workflow } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Skeleton } from '@/components/ui/skeleton';
import { usePermissions } from '@/features/auth/permissions';
import { exportOntologyTurtle, useGraph, type OntologySummary } from '@/features/ontologies/api';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { useErrorMessage } from '@/i18n/error-message';
import { downloadText } from '@/lib/download';

import { ElementDetailSheet } from './element-detail-sheet';
import { ElementList } from './element-list';
import { GraphView } from './graph-view';

export type OntologyView = 'graph' | 'list';

interface OntologyPageProps {
  ontologyId: string | undefined;
  view: OntologyView;
  onOntologyChange: (id: string) => void;
  onViewChange: (view: OntologyView) => void;
}

export function OntologyPage({ ontologyId, view, onOntologyChange, onViewChange }: OntologyPageProps) {
  const { t } = useTranslation();
  const toast = useToast();
  const message = useErrorMessage();
  const { canUpload } = usePermissions();
  const { query, ontologies, selected } = useSelectedOntology(ontologyId);
  const [elementId, setElementId] = useState<string | null>(null);

  const exportTurtle = useMutation({
    mutationFn: (ontology: OntologySummary) => exportOntologyTurtle(ontology.id).then((text) => ({ ontology, text })),
    onSuccess: ({ ontology, text }) => {
      downloadText(`${ontology.key}.ttl`, text);
      toast.success(t('ontologyPage.exported'));
    },
    onError: (error) => toast.error(t('ontologyPage.exportFailed'), message(error)),
  });

  return (
    <>
      <PageHeader
        title={t('nav.ontology')}
        info={t('pages.ontology.info')}
        actions={
          selected && ontologies ? (
            <>
              <OntologySelector
                ontologies={ontologies}
                value={selected.id}
                onValueChange={(id) => {
                  setElementId(null);
                  onOntologyChange(id);
                }}
              />
              <SegmentedControl
                legend={t('ontologyPage.viewLabel')}
                hideLegend
                value={view}
                onValueChange={onViewChange}
                options={[
                  { value: 'graph', label: t('ontologyPage.viewGraph'), icon: <Workflow aria-hidden /> },
                  { value: 'list', label: t('ontologyPage.viewList'), icon: <List aria-hidden /> },
                ]}
              />
              <Button variant="secondary" loading={exportTurtle.isPending} onClick={() => exportTurtle.mutate(selected)}>
                {exportTurtle.isPending ? null : <Download aria-hidden />}
                {t('ontologyPage.exportTurtle')}
              </Button>
            </>
          ) : null
        }
      />

      <QueryState query={query}>
        {(list) =>
          list.length === 0 || !selected ? (
            <Card>
              <EmptyState
                icon={Network}
                tone="info"
                title={t('ontologyPage.noOntologyTitle')}
                description={t('ontologyPage.noOntologyDescription')}
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
            <div className="space-y-4">
              <OntologyStats ontology={selected} />
              {view === 'list' ? (
                <ElementList key={selected.id} ontologyId={selected.id} onSelect={setElementId} />
              ) : (
                <GraphPanel ontology={selected} canUpload={canUpload} onSelect={setElementId} />
              )}
              <ElementDetailSheet ontologyId={selected.id} elementId={elementId} onSelect={setElementId} onClose={() => setElementId(null)} />
            </div>
          )
        }
      </QueryState>
    </>
  );
}

function OntologyStats({ ontology }: { ontology: OntologySummary }) {
  const { t } = useTranslation();
  const stats = [
    { key: 'entityTypes', value: ontology.entityTypeCount, className: 'bg-primary-soft text-primary-strong' },
    { key: 'relationTypes', value: ontology.relationTypeCount, className: 'bg-secondary-soft text-secondary-strong' },
    { key: 'properties', value: ontology.propertyCount, className: 'bg-success-soft text-success-strong' },
  ] as const;
  return (
    <dl className="flex flex-wrap gap-3 text-sm">
      {stats.map((stat) => (
        <div key={stat.key} className={`flex items-baseline gap-2 rounded-lg px-3 py-1.5 ${stat.className}`}>
          <dt>{t(`ontologyPage.stats.${stat.key}`)}</dt>
          <dd className="text-base font-semibold tabular-nums">{stat.value}</dd>
        </div>
      ))}
      <div className="flex items-baseline gap-2 rounded-lg bg-muted px-3 py-1.5 text-muted-foreground">
        <dt>{t('ontologyPage.stats.activeRelease')}</dt>
        <dd className="font-semibold text-foreground">
          {ontology.activeReleaseVersion !== null ? t('releases.versionLabel', { version: ontology.activeReleaseVersion }) : t('ontologyPage.stats.noRelease')}
        </dd>
      </div>
    </dl>
  );
}

function GraphPanel({ ontology, canUpload, onSelect }: { ontology: OntologySummary; canUpload: boolean; onSelect: (id: string) => void }) {
  const { t } = useTranslation();
  const query = useGraph(ontology.id);
  return (
    <QueryState query={query} loading={<Skeleton className="h-[min(70dvh,44rem)] min-h-96 rounded-xl" />}>
      {(graph) =>
        graph.nodes.length === 0 ? (
          <Card>
            <EmptyState
              icon={Workflow}
              tone="info"
              title={t('ontologyPage.graph.emptyTitle')}
              description={t('ontologyPage.graph.emptyDescription')}
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
          <GraphView graph={graph} onSelect={onSelect} />
        )
      }
    </QueryState>
  );
}

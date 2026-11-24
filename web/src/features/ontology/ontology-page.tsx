import { useMutation } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
  ArrowRightLeft,
  Box,
  Braces,
  ChevronDown,
  Download,
  Ellipsis,
  FileCode,
  FilePlus,
  FileUp,
  List,
  Network,
  Plus,
  ShieldCheck,
  Tag,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip } from '@/components/ui/tooltip';
import { usePublishAssistantSelection } from '@/features/assistant/assistant-selection';
import { usePermissions } from '@/features/auth/permissions';
import { exportOntologyTurtle, useGraph, type OntologySummary } from '@/features/ontologies/api';
import { CreateOntologyDialog, type CreateMethod } from '@/features/ontologies/create-ontology-dialog';
import { ImportOwlDialog } from '@/features/ontologies/import-owl';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { useErrorMessage } from '@/i18n/error-message';
import { downloadText } from '@/lib/download';

import { AxiomFormDialog } from './axiom-form-dialog';
import { ElementDetailSheet } from './element-detail-sheet';
import { FORM_KINDS, type FormKind } from './element-form';
import { ElementFormDialog } from './element-form-dialog';
import { ElementList } from './element-list';
import { GraphView } from './graph-view';
import { TurtleView } from './turtle-view';

export type OntologyView = 'graph' | 'list' | 'turtle';

const kindIcons: Record<FormKind, LucideIcon> = {
  entity_type: Box,
  relation_type: ArrowRightLeft,
  property: Tag,
  constraint: ShieldCheck,
};

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
  // Which create method the "new ontology" dialog opens with; null while it is closed.
  const [creating, setCreating] = useState<CreateMethod | null>(null);
  const [importing, setImporting] = useState(false);
  // The kind of element being created by hand; null while the form is closed.
  const [newKind, setNewKind] = useState<FormKind | null>(null);
  const [newAxiom, setNewAxiom] = useState(false);
  // The element last opened stays the assistant's context after its (modal) sheet closes, since the
  // assistant cannot be used while the sheet is open.
  const [contextElementId, setContextElementId] = useState<string | null>(null);
  usePublishAssistantSelection({ ontologyId: selected?.id, elementId: contextElementId });

  const selectElement = (id: string | null) => {
    setElementId(id);
    if (id) setContextElementId(id);
  };

  const switchOntology = (id: string) => {
    setElementId(null);
    setContextElementId(null);
    onOntologyChange(id);
  };

  const exportTurtle = useMutation({
    mutationFn: (ontology: OntologySummary) => exportOntologyTurtle(ontology.id).then((text) => ({ ontology, text })),
    onSuccess: ({ ontology, text }) => {
      downloadText(`${ontology.key}.ttl`, text);
      toast.success(t('ontologyPage.exported'));
    },
    onError: (error) => toast.error(t('ontologyPage.exportFailed'), message(error)),
  });

  const moreLabel = t('ontologyPage.moreActions');

  return (
    <>
      <PageHeader
        title={t('nav.ontology')}
        info={t('pages.ontology.info')}
        actions={
          selected && ontologies ? (
            <>
              <OntologySelector ontologies={ontologies} value={selected.id} onValueChange={switchOntology} />
              <SegmentedControl
                legend={t('ontologyPage.viewLabel')}
                hideLegend
                value={view}
                onValueChange={onViewChange}
                options={[
                  { value: 'graph', label: t('ontologyPage.viewGraph'), icon: <Workflow aria-hidden /> },
                  { value: 'list', label: t('ontologyPage.viewList'), icon: <List aria-hidden /> },
                  { value: 'turtle', label: t('ontologyPage.viewTurtle'), icon: <FileCode aria-hidden /> },
                ]}
              />
              <DropdownMenu>
                <Tooltip content={moreLabel}>
                  <DropdownMenuTrigger aria-label={moreLabel} className={buttonVariants({ variant: 'secondary', size: 'icon' })}>
                    <Ellipsis aria-hidden />
                  </DropdownMenuTrigger>
                </Tooltip>
                <DropdownMenuContent className="min-w-52">
                  {canUpload ? (
                    <>
                      <DropdownMenuItem onClick={() => setCreating('blank')}>
                        <FilePlus aria-hidden />
                        {t('ontologyPage.newOntology')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setImporting(true)}>
                        <FileUp aria-hidden />
                        {t('ontologyPage.importOwl')}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                    </>
                  ) : null}
                  <DropdownMenuItem disabled={exportTurtle.isPending} onClick={() => exportTurtle.mutate(selected)}>
                    <Download aria-hidden />
                    {t('ontologyPage.exportTurtle')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              {canUpload ? (
                <DropdownMenu>
                  <DropdownMenuTrigger className={buttonVariants({ variant: 'primary' })}>
                    <Plus aria-hidden />
                    {t('ontologyPage.edit.create')}
                    <ChevronDown aria-hidden />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="min-w-44">
                    {FORM_KINDS.map((kind) => {
                      const Icon = kindIcons[kind];
                      return (
                        <DropdownMenuItem key={kind} onClick={() => setNewKind(kind)}>
                          <Icon aria-hidden />
                          {t(`kind.${kind}`)}
                        </DropdownMenuItem>
                      );
                    })}
                    <DropdownMenuItem onClick={() => setNewAxiom(true)}>
                      <Braces aria-hidden />
                      {t('kind.axiom')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
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
                    <div className="flex flex-wrap justify-center gap-2">
                      <Link to="/documents" className={buttonVariants({ variant: 'primary' })}>
                        {t('documents.upload')}
                      </Link>
                      <Button variant="secondary" onClick={() => setCreating('import')}>
                        <FileUp aria-hidden />
                        {t('ontologyPage.importOwlFile')}
                      </Button>
                    </div>
                  ) : undefined
                }
              />
            </Card>
          ) : (
            <div className="space-y-4">
              <OntologyStats ontology={selected} />
              {view === 'turtle' ? (
                <TurtleView key={selected.id} ontology={selected} />
              ) : view === 'list' ? (
                <ElementList key={selected.id} ontologyId={selected.id} onSelect={selectElement} />
              ) : (
                <GraphPanel ontology={selected} canUpload={canUpload} onSelect={selectElement} />
              )}
              <ElementDetailSheet ontologyId={selected.id} elementId={elementId} onSelect={selectElement} onClose={() => setElementId(null)} />
            </div>
          )
        }
      </QueryState>

      {canUpload ? (
        <>
          <CreateOntologyDialog
            open={creating !== null}
            onOpenChange={(open) => {
              if (!open) setCreating(null);
            }}
            allowImport
            initialMethod={creating ?? 'blank'}
            onCreated={(ontology) => {
              setCreating(null);
              toast.success(t('ontologyPage.created', { name: ontology.name }));
              switchOntology(ontology.id);
            }}
            onImported={(result) => switchOntology(result.ontology.id)}
          />
          {selected ? <ImportOwlDialog ontology={selected} open={importing} onOpenChange={setImporting} /> : null}
          {selected ? <ElementFormDialog ontologyId={selected.id} target={newKind ? { kind: newKind } : null} onClose={() => setNewKind(null)} /> : null}
          {selected ? <AxiomFormDialog ontologyId={selected.id} open={newAxiom} onClose={() => setNewAxiom(false)} /> : null}
        </>
      ) : null}
    </>
  );
}

function OntologyStats({ ontology }: { ontology: OntologySummary }) {
  const { t } = useTranslation();
  const stats = [
    { key: 'entityTypes', value: ontology.entityTypeCount, className: 'bg-primary-soft text-primary-strong' },
    { key: 'relationTypes', value: ontology.relationTypeCount, className: 'bg-secondary-soft text-secondary-strong' },
    { key: 'properties', value: ontology.propertyCount, className: 'bg-success-soft text-success-strong' },
    { key: 'constraints', value: ontology.constraintCount, className: 'bg-muted text-muted-foreground' },
    { key: 'axioms', value: ontology.axiomCount, className: 'bg-muted text-muted-foreground' },
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

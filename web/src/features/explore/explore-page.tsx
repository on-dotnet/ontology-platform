import { Link } from '@tanstack/react-router';
import { Boxes, Compass } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/states/empty-state';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { TabsList, TabsPanel, TabsTrigger } from '@/components/ui/tabs';
import { usePublishAssistantSelection } from '@/features/assistant/assistant-selection';
import { usePermissions } from '@/features/auth/permissions';
import { MetricsPanel } from '@/features/metrics/metrics-panel';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { AskPanel } from '@/features/qa/ask-panel';
import { storage } from '@/lib/storage';

import { useExploreOntologies, useTypes } from './api';
import type { Criteria } from './object-table';
import { QueryResult, ReleaseChangedNotice } from './query-result';
import { TypeBrowser, TypeList } from './type-browser';

const selectedOntologyKey = 'op.explore.ontology';
const emptyCriteria: Criteria = { filters: [], sort: [] };

function ReleaseScope({ releaseId, onRestart, children }: { releaseId: string; onRestart: () => void; children: ReactNode }) {
  const [browsingRelease] = useState(releaseId);
  return browsingRelease === releaseId ? <div className="space-y-4">{children}</div> : <ReleaseChangedNotice onRestart={onRestart} />;
}

function PublishedObjects({ ontologyId: id }: { ontologyId: string }) {
  const { t } = useTranslation();
  const { canEditBindings } = usePermissions();
  const [refresh, setRefresh] = useState(0);
  const query = useTypes(id, refresh);
  const [selection, setSelection] = useState<{ typeId: string; criteria: Criteria }>();
  const restart = () => setRefresh((n) => n + 1);
  return (
    <QueryResult query={query} id={id} onRestart={restart} keepMetadata>
      {({ items, release }) => {
        const selected = items.find((type) => type.typeId === selection?.typeId && !type.problem) ?? items.find((type) => !type.problem);
        const previous = selection && selection.typeId === selected?.typeId ? selection.criteria : emptyCriteria;
        // A newly active release can remove a binding or change its supported operators.
        const criteria: Criteria = {
          filters: previous.filters.filter((f) => selected?.properties.some((p) => p.propertyId === f.propertyId && p.ops.includes(f.op))),
          sort: previous.sort.filter((s) => selected?.properties.some((p) => p.propertyId === s.propertyId)),
        };
        return (
          <ReleaseScope key={refresh} releaseId={release.id} onRestart={restart}>
            <Badge tone="secondary">{t('explore.version', { version: release.version })}</Badge>
            {items.length === 0 ? (
              <Card><EmptyState icon={Boxes} title={t('explore.noBindings')} action={canEditBindings && (
                <Link to="/ontology" search={{ ontology: id, view: 'list' }} className={buttonVariants()}>{t('explore.bind')}</Link>
              )} /></Card>
            ) : (
              <div className="grid items-start gap-6 lg:grid-cols-4">
                <TypeList types={items} selected={selected?.typeId} onSelect={(typeId) => {
                  if (typeId !== selected?.typeId) setSelection({ typeId, criteria: emptyCriteria });
                }} />
                {selected ? (
                  <TypeBrowser key={selected.typeId} id={id} releaseId={release.id}
                    types={items} type={selected} criteria={criteria} onRestart={restart}
                    onChange={(next) => setSelection({ typeId: selected.typeId, criteria: next })} />
                ) : <Card className="lg:col-span-3"><EmptyState icon={Boxes} tone="warning" title={t('explore.noAvailableTypes')} /></Card>}
              </div>
            )}
          </ReleaseScope>
        );
      }}
    </QueryResult>
  );
}

const tabs = [
  { value: 'objects', Panel: PublishedObjects },
  { value: 'ask', Panel: AskPanel },
  { value: 'metrics', Panel: MetricsPanel },
] as const;

export type ExploreTab = (typeof tabs)[number]['value'];

export function isExploreTab(value: unknown): value is ExploreTab {
  return tabs.some((tab) => tab.value === value);
}

export function ExplorePage() {
  const { t } = useTranslation();
  const [requested, setRequested] = useState(() => storage.get(selectedOntologyKey));
  const query = useExploreOntologies();
  const selected = query.data?.find((ontology) => ontology.id === requested) ?? query.data?.[0];
  usePublishAssistantSelection({ ontologyId: selected?.id });
  return (
    <>
      <PageHeader title={t('explore.title')} info={t('explore.publishedHint')}
        actions={selected && query.data && !query.error && <OntologySelector ontologies={query.data} value={selected.id} onValueChange={(id) => {
          storage.set(selectedOntologyKey, id);
          setRequested(id);
        }} />} />
      <TabsList activateOnFocus aria-label={t('explore.title')} className="mb-6">
        {tabs.map(({ value }) => (
          <TabsTrigger key={value} value={value}>{t(`explore.tabs.${value}`)}</TabsTrigger>
        ))}
      </TabsList>
      {tabs.map(({ value, Panel }) => (
        <TabsPanel key={value} value={value}>
          <QueryResult query={query} keepMetadata>
            {() => selected ? <Panel key={selected.id} ontologyId={selected.id} /> : (
              <Card><EmptyState icon={Compass} title={t('explore.noOntologies')} /></Card>
            )}
          </QueryResult>
        </TabsPanel>
      ))}
    </>
  );
}

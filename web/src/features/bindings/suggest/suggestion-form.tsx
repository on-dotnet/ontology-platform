import { useRouterState } from '@tanstack/react-router';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { useSource, useSourceList, type DataSource } from '@/features/datasources/api';
import { OntologySelector } from '@/features/ontologies/ontology-selector';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';

import { ScopePicker } from './scope-picker';

type Body = components['schemas']['BindingSuggestionCreate'];

interface Props {
  ontologyId?: string;
  dataSourceId?: string;
  disabled: boolean;
  onSubmit: (ontologyId: string, body: Body) => void;
}

export function SuggestionForm({ ontologyId, dataSourceId, disabled, onSubmit }: Props) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState<string>();
  const search = useRouterState({ select: (state) => state.location.search as Record<string, unknown> });
  const { query, selected } = useSelectedOntology(choice ?? (typeof search.ontology === 'string' ? search.ontology : undefined));
  const target = ontologyId ?? selected?.id;
  const controls = {
    disabled,
    onSubmit: (body: Body) => { if (target) onSubmit(target, body); },
  };

  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-4">
      {!ontologyId && (
        <QueryState query={query}>
          {(ontologies) => selected
            ? <OntologySelector ontologies={ontologies} value={selected.id} onValueChange={setChoice} />
            : <p className="text-sm text-muted-foreground">{t('bindings.suggest.noOntologies')}</p>}
        </QueryState>
      )}
      {target && (ontologyId || query.isSuccess) && (
        dataSourceId
          ? <KnownSource key={dataSourceId} id={dataSourceId} {...controls} />
          : <ChooseSource {...controls} />
      )}
    </fieldset>
  );
}

type SourceControls = { disabled: boolean; onSubmit: (body: Body) => void };

function KnownSource({ id, ...controls }: SourceControls & { id: string }) {
  const { t } = useTranslation();
  const query = useSource(id, true);
  return (
    <QueryState query={query} requiredRole="editor">
      {(source) => {
        if (source.status === 'archived') return <InlineNotice tone="error">{t('errors.datasource.archived')}</InlineNotice>;
        if (source.catalog?.status !== 'ready') return <InlineNotice tone="error">{t('errors.catalog.not_ready')}</InlineNotice>;
        return <SourceScope source={source} {...controls} />;
      }}
    </QueryState>
  );
}

function ChooseSource(controls: SourceControls) {
  const { t } = useTranslation();
  const id = useId();
  const [chosenId, setChosenId] = useState('');
  const query = useSourceList();
  return (
    <QueryState query={query} requiredRole="editor">
      {(sources) => {
        const ready = sources.filter((source) => source.status === 'active' && source.catalog?.status === 'ready');
        const chosen = ready.find((source) => source.id === chosenId);
        if (!ready.length) return <p className="text-sm text-muted-foreground">{t('bindings.suggest.noSources')}</p>;
        return (
          <>
            <div className="space-y-1">
              <Label htmlFor={id} required>{t('bindings.form.dataSource')}</Label>
              <NativeSelect id={id} required value={chosen?.id ?? ''} onChange={(event) => setChosenId(event.target.value)}>
                <option value="">{t('bindings.form.dataSourcePlaceholder')}</option>
                {ready.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
              </NativeSelect>
            </div>
            {chosen && <SourceScope key={chosen.id} source={chosen} {...controls} />}
          </>
        );
      }}
    </QueryState>
  );
}

function SourceScope({ source, disabled, onSubmit }: SourceControls & { source: DataSource }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {t(source.allowSamples ? 'bindings.suggest.modelInputsWithSamples' : 'bindings.suggest.modelInputs')}
      </p>
      {source.allowSamples && <InlineNotice tone="warning">{t('bindings.suggest.sampleEvidence')}</InlineNotice>}
      <ScopePicker source={source} disabled={disabled} onSubmit={(scope) => onSubmit({ dataSourceId: source.id, ...scope })} />
    </div>
  );
}

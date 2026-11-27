import { useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isForbidden } from '@/api/errors';
import { InfoTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { ErrorState } from '@/components/states/error-state';
import { ForbiddenState } from '@/components/states/forbidden-state';
import { QueryState } from '@/components/states/query-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { Skeleton } from '@/components/ui/skeleton';
import { listKey, useSourceList } from '@/features/datasources/api';
import { elementName, useElements, type EditItem, type Element } from '@/features/ontologies/api';
import { useSaveEdits, useSaveErrorMessage } from '@/features/ontology/edit-actions';

import {
  bindingKeys, canBeKey, columnFits, useBindingViews, useCatalogTable,
  type CatalogTable, type DataSource, type TypeBindingView,
} from './api';
import { bindingEdits, bindingModel, defaultChoices, joinProblem, replacementChanged, withKeys, type BindingModel, type Choices } from './binding-edits';
import { CatalogTablePicker, type TableChoice } from './catalog-table-picker';
import { RelationJoinEditor } from './relation-join-editor';

interface DialogProps {
  ontologyId: string;
  type: Element;
  all: readonly Element[];
  view: TypeBindingView;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BindingDialog({ open, onOpenChange, ontologyId, type, all, view }: DialogProps) {
  const { t, i18n } = useTranslation();
  // Shared with the data page, so what changes there shows here.
  const sources = useSourceList();
  const views = useBindingViews(ontologyId);
  const editing = view.table ? ontologyId : undefined;
  const properties = useElements(editing, { kind: 'property_binding' });
  const relations = useElements(editing, { kind: 'relation_binding' });
  const { mutation, apply } = useSaveEdits(ontologyId);
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ error: unknown } | { changed: true } | null>(null);
  const message = useSaveErrorMessage();
  const client = useQueryClient();
  const title = t(view.table ? 'bindings.form.editTitle' : 'bindings.form.createTitle', {
    type: elementName(type, i18n.resolvedLanguage ?? i18n.language),
  });
  const queries = editing ? [sources, views, properties, relations] : [sources, views];
  const failedQuery = queries.find((query) => query.isError);
  const forbidden = queries.some((query) => isForbidden(query.error));
  const availableSources = sources.data;
  const boundViews = views.data;
  // The form picks the bound source once, so it waits for a list fetched by this opening rather than a
  // cached one. A later refetch that fails keeps the form.
  const [listed, setListed] = useState(false);
  if (!listed && sources.isFetchedAfterMount && sources.isSuccess) setListed(true);
  const ready = availableSources !== undefined && listed && boundViews !== undefined &&
    (!editing || (properties.data !== undefined && relations.data !== undefined));
  const refresh = () => Promise.all([bindingKeys.all, listKey].map((queryKey) => client.invalidateQueries({ queryKey })));
  async function save(items: EditItem[], model: BindingModel) {
    if (saving.current) return;
    if (!items.length) {
      onOpenChange(false);
      return;
    }
    saving.current = true;
    setBusy(true);
    setFailure(null);
    try {
      if (items.some((item) => item.op === 'delete' && item.kind === 'type_binding')) {
        // The server expands a cascade. Detect dependencies added since this dialog opened.
        const [tables, columns, joins] = await Promise.all([
          views.refetch({ throwOnError: true }), properties.refetch({ throwOnError: true }), relations.refetch({ throwOnError: true }),
        ]);
        const latestViews = tables.data ?? [];
        const current = latestViews.find((item) => item.typeId === type.id);
        const latest = current && bindingModel(type, all, current, latestViews, columns.data ?? [], joins.data ?? []);
        if (!latest || replacementChanged(model, latest, items)) {
          setFailure({ changed: true });
          await refresh();
          return;
        }
      }
      await mutation.mutateAsync({ items, appliedTitle: t('bindings.form.saved') });
      await refresh();
      onOpenChange(false);
    } catch (error) {
      setFailure({ error });
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!saving.current) onOpenChange(next); }}>
      <DialogContent closeLabel={t('common.close')} className="max-h-[calc(100dvh-2rem)] w-[min(46rem,calc(100vw-2rem))] overflow-y-auto">
        <DialogTitle className="pr-8">{ready || failedQuery ? title : t('common.loading')}</DialogTitle>
        {forbidden ? <ForbiddenState requiredRole="editor" /> : (
          <>
            {failedQuery && <ErrorState error={failedQuery.error} onRetry={() => void failedQuery.refetch()} />}
            {ready ? (
              <BindingForm type={type} all={all} view={view} views={boundViews} sources={availableSources}
                propertyBindings={properties.data ?? []} relationBindings={relations.data ?? []} apply={apply} pending={busy}
                serverError={failure ? ('changed' in failure ? t('bindings.form.dependenciesChanged') : message(failure.error)) : undefined}
                onSave={save} />
            ) : !failedQuery && <Skeleton className="mt-4 h-40 rounded-lg" />}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  type: Element;
  all: readonly Element[];
  view: TypeBindingView;
  views: TypeBindingView[];
  sources: DataSource[];
  propertyBindings: Element[];
  relationBindings: Element[];
  apply: boolean;
  pending: boolean;
  serverError?: string;
  onSave: (items: EditItem[], model: BindingModel) => Promise<void>;
}

function BindingForm({ type, all, view, views, sources, propertyBindings, relationBindings, apply, pending, serverError, onSave }: FormProps) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const language = i18n.resolvedLanguage ?? i18n.language;
  // Compare against the revisions the editor saw, even after a background refetch.
  const [model] = useState(() => bindingModel(type, all, view, views, propertyBindings, relationBindings));
  const activeSources = sources.filter((item) => item.status === 'active');
  const initialSource = activeSources.find((item) => item.id === model.original?.dataSource.id);
  const [sourceId, setSourceId] = useState(initialSource?.id ?? '');
  const [selected, setSelected] = useState<TableChoice | null>(() => initialSource && model.original
    ? { schema: model.original.schema, name: model.original.table } : null);
  const [edits, setEdits] = useState<Partial<Choices>>({});
  const [submitted, setSubmitted] = useState(false);
  const [touchedSource, setTouchedSource] = useState(false);
  const [touchedKeys, setTouchedKeys] = useState(false);
  const source = activeSources.find((item) => item.id === sourceId);
  // The list is newer than the view when the data page archives the source while this dialog is open.
  const bound = model.original?.dataSource;
  const archivedSource = bound && (sources.find((item) => item.id === bound.id) ?? bound).status === 'archived' ? bound : undefined;
  const ready = source?.catalog?.status === 'ready';
  const detail = useCatalogTable(ready ? sourceId : undefined, selected?.schema, selected?.name);
  const table = detail.isSuccess ? detail.data : undefined;
  const choices = table ? { ...defaultChoices(model, sourceId, table), ...edits } : undefined;
  const keyError = choices && (!choices.keys.length ? 'keyRequired' : choices.keys.length > 8 ? 'keyTooMany' : undefined);
  const joinErrors = new Map<string, string>();
  if (choices) {
    for (const slot of model.relations) {
      const join = choices.joins[slot.key];
      if (!join) continue;
      const ownKeys = choices.keys.length;
      const otherKeys = slot.otherId === model.typeId ? ownKeys : slot.other?.keyColumns.length;
      if (otherKeys === undefined) continue;
      const sourceKeys = slot.isDomain ? ownKeys : otherKeys;
      const targetKeys = slot.isDomain ? otherKeys : ownKeys;
      const error = joinProblem(join, sourceKeys, targetKeys);
      if (error) joinErrors.set(slot.key, t(`bindings.form.errors.${error}`, { sourceKeys, targetKeys }));
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (pending || !ready || !table || !choices || keyError || joinErrors.size) return;
    void onSave(bindingEdits(model, sourceId, table, choices), model);
  }
  const sourceError = !source && (submitted || touchedSource);
  const tableError = submitted && ready && !selected;
  const count = Number(!source) + Number(ready && !selected) + Number(Boolean(keyError)) + joinErrors.size;
  return (
    <form noValidate inert={pending} onSubmit={submit} className="mt-4 space-y-4">
      <InlineNotice tone="warning" title={t('bindings.form.visibility.title')} announce={false}>
        {t('bindings.form.visibility.description')}
      </InlineNotice>
      {submitted && count > 0 && <InlineNotice tone="error">{t('review.edit.validationSummary', { count })}</InlineNotice>}
      {serverError && <InlineNotice tone="error">{serverError}</InlineNotice>}
      {archivedSource && (
        <InlineNotice tone="warning" title={t('bindings.form.sourceArchived.title')}>
          {t('bindings.form.sourceArchived.description', { name: archivedSource.name })}
        </InlineNotice>
      )}
      <div className="space-y-1">
        <Label htmlFor={id} required>{t('bindings.form.dataSource')}</Label>
        <NativeSelect id={id} aria-label={t('bindings.form.dataSource')} aria-required aria-invalid={sourceError || undefined}
          aria-describedby={sourceError ? `${id}-error` : undefined} value={source?.id ?? ''}
          onBlur={() => setTouchedSource(true)} onChange={(event) => {
            setSourceId(event.target.value);
            setSelected(null);
            setEdits({});
            setTouchedKeys(false);
          }}>
          <option value="">{t('bindings.form.dataSourcePlaceholder')}</option>
          {activeSources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </NativeSelect>
        {sourceError && <p id={`${id}-error`} className="text-sm text-error-strong">{t('bindings.form.errors.dataSourceRequired')}</p>}
        {!activeSources.length && <p className="text-sm text-muted-foreground">{t('bindings.form.noDataSources')}</p>}
      </div>
      {source && !ready && <InlineNotice tone="warning">{t('bindings.form.catalogNotReady')}</InlineNotice>}
      {ready && (
        <CatalogTablePicker key={sourceId} dataSourceId={sourceId} label={t('bindings.form.table')} value={selected}
          error={tableError ? t('bindings.form.errors.tableRequired') : undefined}
          onChange={(next) => {
            if (next.schema === selected?.schema && next.name === selected.name) return;
            setSelected(next);
            setEdits({});
            setTouchedKeys(false);
          }}
        />
      )}
      {ready && selected && (
        <QueryState query={detail} loading={<Skeleton className="h-32 rounded-lg" />}>
          {(table) => choices && (
            <>
              <KeyFields table={table} keys={choices.keys}
                onChange={(keys) => setEdits(withKeys(model, choices, keys))} onBlur={() => setTouchedKeys(true)}
                error={(submitted || touchedKeys) && keyError ? t(`bindings.form.errors.${keyError}`) : undefined} />
              <PropertyFields model={model} table={table} values={choices.columns} language={language}
                onChange={(key, value) => setEdits({ ...edits, columns: { ...choices.columns, [key]: value } })} />
              {model.relations.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold">{t('bindings.form.relationsTitle')} <InfoTip>{t('bindings.form.relationsHint')}</InfoTip></h3>
                  {model.relations.map((slot) => {
                    const self = slot.otherId === type.id;
                    const other = self ? { schema: table.schema, table: table.name, keyColumns: choices.keys } : slot.other;
                    const otherType = all.find((item) => item.id === slot.otherId);
                    const otherName = otherType ? elementName(otherType, language) : t('review.unknownType');
                    const relation = elementName(slot.subject, language);
                    const multiplePairs = model.relations.some((item) => item !== slot && item.subject.id === slot.subject.id);
                    const name = multiplePairs
                      ? t(slot.isDomain ? 'bindings.relations.out' : 'bindings.relations.in', { relation, type: otherName })
                      : relation;
                    if (!other || (!self && slot.other?.dataSource.id !== sourceId)) {
                      return (
                        <div key={slot.key} className="text-sm">
                          <span className="font-medium">{name}</span>
                          <p className="text-muted-foreground">{other ? t('errors.binding.cross_source') : t('bindings.form.otherTypeUnbound', { type: otherName })}</p>
                        </div>
                      );
                    }
                    return (
                      <RelationJoinEditor key={slot.key} name={name} dataSourceId={sourceId} own={table} ownKeys={choices.keys}
                        other={other} isDomain={slot.isDomain} value={choices.joins[slot.key] ?? null}
                        onChange={(join) => setEdits({ ...edits, joins: { ...choices.joins, [slot.key]: join } })}
                        error={submitted ? joinErrors.get(slot.key) : undefined} />
                    );
                  })}
                </section>
              )}
            </>
          )}
        </QueryState>
      )}
      <DialogDescription>{t(apply ? 'bindings.form.appliesAtOnce' : 'bindings.form.submitsForReview')}</DialogDescription>
      <div className="flex justify-end gap-2">
        <DialogClose disabled={pending} className={buttonVariants({ variant: 'secondary' })}>{t('common.cancel')}</DialogClose>
        <Button type="submit" loading={pending} disabled={Boolean(source && (!ready || (selected && !table)))}>{t('bindings.form.save')}</Button>
      </div>
    </form>
  );
}

function KeyFields({ table, keys, onChange, onBlur, error }: {
  table: CatalogTable; keys: string[]; onChange: (keys: string[]) => void; onBlur: () => void; error?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  const allowed = table.columns.filter(canBeKey);
  const unavailable = keys.filter((key) => !allowed.some((column) => column.name === key));
  const remove = (name: string) => onChange(keys.filter((key) => key !== name));
  return (
    <fieldset className="space-y-2" aria-label={t('bindings.form.keyColumns')}
      aria-invalid={error ? true : undefined} aria-describedby={error ? id : undefined}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) onBlur(); }}>
      <legend className="text-sm font-semibold">
        {t('bindings.form.keyColumns')} <span aria-hidden className="text-error-strong">*</span> <InfoTip>{t('bindings.form.keyColumnsHint')}</InfoTip>
      </legend>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {allowed.map(({ name }) => (
          <label key={name} className="inline-flex items-center gap-2 font-mono text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={keys.includes(name)}
              onChange={(event) => { if (event.target.checked) onChange([...keys, name]); else remove(name); }} />
            {name}
          </label>
        ))}
      </div>
      {unavailable.map((name) => (
        <div key={name} className="flex items-center gap-2 text-sm text-warning-strong">
          {t('bindings.form.unavailableKey', { column: name })}
          <Button variant="secondary" size="sm" onClick={() => remove(name)}>{t('bindings.form.removeKey')}</Button>
        </div>
      ))}
      {keys.length > 1 && <p className="font-mono text-xs text-muted-foreground">{keys.join(t('common.listSeparator'))}</p>}
      {error && <p id={id} className="text-sm text-error-strong">{error}</p>}
    </fieldset>
  );
}

function PropertyFields({ model, table, values, language, onChange }: {
  model: BindingModel; table: CatalogTable; values: Choices['columns']; language: string;
  onChange: (key: string, value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  if (!model.properties.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{t('bindings.form.propertiesTitle')} <InfoTip>{t('bindings.form.propertiesHint')}</InfoTip></h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {model.properties.map(({ subject }) => {
          const label = elementName(subject, language);
          const fieldId = `${id}-${subject.id}`;
          const compatible = table.columns.filter((col) => columnFits(subject.datatype, col));
          const value = values[subject.id] ?? '';
          const stale = value && !compatible.some((col) => col.name === value);
          return (
            <div key={subject.id} className="space-y-1">
              <label htmlFor={fieldId} className="block text-sm font-medium">{label}</label>
              <NativeSelect id={fieldId} value={stale ? '' : value} disabled={!compatible.length}
                onChange={(event) => onChange(subject.id, event.target.value)}>
                <option value="">{t('bindings.form.noColumn')}</option>
                {compatible.map((col) => <option key={col.name} value={col.name}>{col.name}</option>)}
              </NativeSelect>
              {!compatible.length && <p className="text-xs text-muted-foreground">{t('bindings.form.noCompatibleColumn')}</p>}
              {stale && (
                <div className="flex flex-wrap items-center gap-2 text-xs text-warning-strong">
                  {t('bindings.form.staleColumn', { column: value })}
                  <Button variant="secondary" size="sm" onClick={() => onChange(subject.id, '')}>{t('bindings.form.noColumn')}</Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { QueryState } from '@/components/states/query-state';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { SegmentedControl } from '@/components/ui/segmented-control';
import type { DataSource } from '@/features/datasources/api';
import { catalogKey } from '@/features/datasources/catalog-browser';
import { usePagination } from '@/lib/pagination';

import { tableName, useCatalogTables, useNextCatalogPage } from '../api';

type Scope = Pick<components['schemas']['BindingSuggestionCreate'], 'schemas' | 'tables'>;
type TableRef = components['schemas']['TableRef'];
type Mode = 'schemas' | 'tables';

interface Props {
  source: DataSource;
  disabled: boolean;
  onSubmit: (scope: Scope) => void;
}

function ScopeOption({ name, detail, checked, onChange }: {
  name: string;
  detail?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-10 items-center gap-2 rounded-md px-2 text-sm hover:bg-muted">
      <input type="checkbox" aria-label={name} checked={checked} onChange={(event) => onChange(event.target.checked)}
        className="size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" />
      <span className="break-all font-mono">{name}</span>
      {detail && <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">{detail}</span>}
    </label>
  );
}

export function ScopePicker({ source, disabled, onSubmit }: Props) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>('schemas');
  const [schemaNames, setSchemaNames] = useState<Set<string> | null>(null);
  const [selectedTables, setSelectedTables] = useState(new Map<string, TableRef>());
  const [search, setSearch] = useState('');
  const [cursors, setCursors] = useState<string[]>([]);
  const bySchema = mode === 'schemas';
  const schemas = useQuery({
    queryKey: [...catalogKey(source.id), source.catalog?.refreshedAt, 'schemas'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/data-sources/{id}/catalog/schemas', {
      params: { path: { id: source.id } }, signal,
    })),
    enabled: bySchema,
  });
  const schemaPage = usePagination(schemas.data?.length ?? 0);
  const cursor = bySchema ? undefined : cursors.at(-1);
  const firstPage = useCatalogTables(bySchema || cursor ? undefined : source.id, search);
  const laterPage = useNextCatalogPage(source.id, search, cursor);
  const tables = cursor ? laterPage : firstPage;

  const selectedSchemas = (schemas.data ?? []).filter(({ name }) => schemaNames === null || schemaNames.has(name));
  const tableCount = bySchema
    ? selectedSchemas.reduce((sum, schema) => sum + schema.tableCount, 0)
    : selectedTables.size;
  const ready = bySchema ? schemas.isSuccess : tables.isSuccess;
  const overSchemaLimit = bySchema && selectedSchemas.length > 50;
  const overTableLimit = tableCount > 200;
  const canSubmit = !disabled && ready && tableCount > 0 && !overSchemaLimit && !overTableLimit;

  function toggleSchema(name: string, checked: boolean) {
    const next = new Set(selectedSchemas.map((schema) => schema.name));
    if (checked) next.add(name);
    else next.delete(name);
    setSchemaNames(next);
  }

  function toggleTable(key: string, table: TableRef, checked: boolean) {
    setSelectedTables((current) => {
      const next = new Map(current);
      if (checked) next.set(key, table);
      else next.delete(key);
      return next;
    });
  }

  function submit() {
    if (canSubmit) onSubmit(bySchema
      ? { schemas: selectedSchemas.map(({ name }) => name) }
      : { tables: [...selectedTables.values()] });
  }

  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-3">
      <SegmentedControl<Mode> legend={t('bindings.suggest.scope')} value={mode} onValueChange={setMode}
        options={[
          { value: 'schemas', label: t('bindings.suggest.bySchema') },
          { value: 'tables', label: t('bindings.suggest.byTable') },
        ]} />
      {bySchema ? (
        <QueryState query={schemas} requiredRole="editor">
          {(items) => items.length ? (
            <>
              <div className="max-h-48 overflow-y-auto rounded-lg border border-border p-1">
                {items.slice(schemaPage.start, schemaPage.end).map(({ name, tableCount: count }) => (
                  <ScopeOption key={name} name={name} detail={t('bindings.suggest.tableCount', { count })}
                    checked={schemaNames === null || schemaNames.has(name)} onChange={(checked) => toggleSchema(name, checked)} />
                ))}
              </div>
              <Pagination state={schemaPage} total={items.length} />
            </>
          ) : <p className="text-sm text-muted-foreground">{t('datasources.catalog.emptySchemas')}</p>}
        </QueryState>
      ) : (
        <>
          <Input type="search" aria-label={t('bindings.form.tableSearch')} placeholder={t('bindings.form.tableSearch')}
            maxLength={128} value={search} onChange={(event) => { setSearch(event.target.value); setCursors([]); }} />
          <QueryState query={tables} requiredRole="editor">
            {({ items, nextCursor }) => (
              <>
                {items.length ? (
                  <div className="max-h-48 overflow-y-auto rounded-lg border border-border p-1">
                    {items.map(({ schema, name }) => {
                      const key = JSON.stringify([schema, name]);
                      return <ScopeOption key={key} name={tableName(schema, name)} checked={selectedTables.has(key)}
                        onChange={(checked) => toggleTable(key, { schema, name }, checked)} />;
                    })}
                  </div>
                ) : <p className="text-sm text-muted-foreground">{t('bindings.form.noTables')}</p>}
                {(cursor || nextCursor) && (
                  <nav aria-label={t('pagination.label')} className="flex justify-end gap-2">
                    <Button size="sm" variant="secondary" disabled={!cursor} onClick={() => setCursors(cursors.slice(0, -1))}>
                      {t('pagination.previous')}
                    </Button>
                    <Button size="sm" variant="secondary" disabled={!nextCursor}
                      onClick={() => { if (nextCursor) setCursors([...cursors, nextCursor]); }}>
                      {t('pagination.next')}
                    </Button>
                  </nav>
                )}
              </>
            )}
          </QueryState>
        </>
      )}
      {ready && overTableLimit && <InlineNotice tone="error">{t('errors.binding_suggestion.scope_too_large')}</InlineNotice>}
      {ready && overSchemaLimit && <InlineNotice tone="error">{t('bindings.suggest.tooManySchemas')}</InlineNotice>}
      <div className="flex flex-wrap items-center justify-end gap-3">
        {ready && <span aria-live="polite" className="text-sm tabular-nums text-muted-foreground">
          {t('bindings.suggest.selectedTableCount', { count: tableCount })}
        </span>}
        <Button disabled={!canSubmit} loading={disabled} onClick={submit}>{t('bindings.suggest.submit')}</Button>
      </div>
    </fieldset>
  );
}

import { useId, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

import { tableName, useCatalogTables, useNextCatalogPage, type CatalogTableBrief } from './api';

export type TableChoice = Pick<CatalogTableBrief, 'schema' | 'name'>;

interface Props {
  dataSourceId: string;
  label: string;
  value: TableChoice | null;
  onChange: (table: TableChoice) => void;
  error?: string;
}

function navigateOptions(event: KeyboardEvent<HTMLDivElement>) {
  const options = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="option"]'));
  const current = options.findIndex((option) => option === event.target);
  if (current < 0) return;
  let next: number;
  switch (event.key) {
    case 'ArrowDown': next = Math.min(current + 1, options.length - 1); break;
    case 'ArrowUp': next = Math.max(current - 1, 0); break;
    case 'Home': next = 0; break;
    case 'End': next = options.length - 1; break;
    default: return;
  }
  event.preventDefault();
  options[next]?.focus();
}

export function CatalogTablePicker({ dataSourceId, label, value, onChange, error }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [search, setSearch] = useState('');
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1);
  const firstPage = useCatalogTables(cursor ? undefined : dataSourceId, search);
  const laterPage = useNextCatalogPage(dataSourceId, search, cursor);
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-semibold">{label} <span aria-hidden className="text-error-strong">*</span></label>
      {value && <span className="font-mono text-sm">{tableName(value.schema, value.name)}</span>}
      <Input
        id={id} type="search" maxLength={128} aria-label={t('bindings.form.tableSearch')}
        aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined}
        placeholder={t('bindings.form.tableSearch')} value={search}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.nativeEvent.isComposing) event.preventDefault();
        }}
        onChange={(event) => { setSearch(event.target.value); setCursors([]); }}
      />
      <QueryState query={cursor ? laterPage : firstPage} requiredRole="editor" loading={<Skeleton className="h-12 rounded-lg" />}>
        {({ items, nextCursor }) => {
          const selectedIndex = items.findIndex((item) => item.schema === value?.schema && item.name === value?.name);
          return (
            <>
              {items.length ? (
                <div
                  role="listbox" aria-label={label} aria-required tabIndex={-1} onKeyDown={navigateOptions}
                  className="max-h-40 overflow-y-auto rounded-lg border border-border"
                >
                  {items.map((item, index) => (
                    <button
                      key={JSON.stringify([item.schema, item.name])} type="button" role="option"
                      aria-selected={index === selectedIndex} tabIndex={index === Math.max(0, selectedIndex) ? 0 : -1}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring aria-selected:bg-primary-soft aria-selected:text-primary-strong"
                      onClick={() => onChange(item)}
                    >
                      <span className="break-all font-mono">{tableName(item.schema, item.name)}</span>
                      {(item.kind === 'view' || item.kind === 'materialized_view') && <Badge>{t('bindings.form.view')}</Badge>}
                    </button>
                  ))}
                </div>
              ) : <p className="text-sm text-muted-foreground">{t('bindings.form.noTables')}</p>}
              {(cursor || nextCursor) && (
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="secondary" disabled={!cursor} onClick={() => setCursors(cursors.slice(0, -1))}>
                    {t('pagination.previous')}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={!nextCursor} onClick={() => { if (nextCursor) setCursors([...cursors, nextCursor]); }}>
                    {t('pagination.next')}
                  </Button>
                </div>
              )}
            </>
          );
        }}
      </QueryState>
      {error && <p id={`${id}-error`} className="text-sm text-error-strong">{error}</p>}
    </div>
  );
}

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Table2 } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { api, type unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { ErrorState } from '@/components/states/error-state';
import { LoadingState } from '@/components/states/loading-state';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/cn';

type CatalogSchema = components['schemas']['CatalogSchema'];
type TableBrief = components['schemas']['CatalogTableBrief'];
type TableAddress = Pick<TableBrief, 'schema' | 'name'>;
type CatalogTable = components['schemas']['CatalogTable'];

export const catalogKey = (id: string) => ['data-source-catalog', id] as const;

interface BrowserProps {
  id: string;
  refreshedAt: string | null;
  unwrapCatalog: typeof unwrap;
}

function TableContents({ table }: { table: CatalogTable }) {
  const { t } = useTranslation();
  const foreignColumns = new Set(table.foreignKeys.flatMap((key) => key.columns));
  return (
    <div className="min-w-0 space-y-4">
      <h3 className="break-all font-semibold">{table.schema}.{table.name}</h3>
      {table.comment && <p className="break-words text-sm">{table.comment}</p>}
      {table.boundType && <Badge tone="primary">{t('datasources.catalog.boundType', { label: table.boundType.label })}</Badge>}
      {table.columns.length ? (
        <div className="overflow-x-auto">
          <Table aria-label={t('datasources.catalog.columns')}>
            <TableHeader>
              <TableRow>
                {(['name', 'type', 'nullable', 'comment'] as const).map((field) => (
                  <TableHead key={field}>{t(`datasources.catalog.${field}`)}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.columns.map((column) => (
                <TableRow key={column.name}>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <span>{column.name}</span>
                      {table.primaryKey?.includes(column.name) && <Badge tone="primary">{t('datasources.catalog.primaryKey')}</Badge>}
                      {foreignColumns.has(column.name) && <Badge tone="secondary">{t('datasources.catalog.foreignKey')}</Badge>}
                    </div>
                  </TableCell>
                  <TableCell>{column.type}</TableCell>
                  <TableCell>{t(column.nullable ? 'datasources.catalog.yes' : 'datasources.catalog.no')}</TableCell>
                  <TableCell>{column.comment}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : <p className="text-sm text-muted-foreground">{t('datasources.catalog.noColumns')}</p>}
      <h4 className="text-sm font-semibold">{t('datasources.catalog.foreignKeys')}</h4>
      {table.foreignKeys.length ? (
        <ul className="space-y-2 text-sm">
          {table.foreignKeys.map((key, index) => (
            <li key={key.name ?? index} className="flex flex-wrap gap-x-3 break-all">
              {key.name && <span className="font-medium">{key.name}</span>}
              <span>{key.columns.join(', ')} → {key.refSchema}.{key.refTable}({key.refColumns.join(', ')})</span>
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-muted-foreground">{t('datasources.catalog.noForeignKeys')}</p>}
    </div>
  );
}

function TableDetail({ id, refreshedAt, unwrapCatalog, table }: BrowserProps & { table: TableAddress }) {
  const detail = useQuery({
    queryKey: [...catalogKey(id), refreshedAt, 'table', table.schema, table.name],
    queryFn: ({ signal }) => unwrapCatalog(api.GET('/api/data-sources/{id}/catalog/tables/{schema}/{table}', {
      params: { path: { id, schema: table.schema, table: table.name } }, signal,
    })),
  });
  return <QueryState query={detail} requiredRole="editor">{(data) => <TableContents table={data} />}</QueryState>;
}

// The tree is flat in the DOM. Levels expose the hierarchy and the arrow keys move one visible row at a time.
function navigateTree(event: KeyboardEvent<HTMLDivElement>) {
  const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="treeitem"]'));
  const current = event.target;
  if (!(current instanceof HTMLButtonElement)) return;
  const index = items.indexOf(current);
  if (index < 0) return;
  const expanded = current.getAttribute('aria-expanded');
  let next: HTMLButtonElement | undefined;
  switch (event.key) {
    case 'ArrowDown': next = items[index + 1]; break;
    case 'ArrowUp': next = items[index - 1]; break;
    case 'Home': next = items[0]; break;
    case 'End': next = items.at(-1); break;
    case 'ArrowRight':
      if (expanded === 'false') current.click();
      else if (expanded === 'true' && items[index + 1]?.getAttribute('aria-level') === '2') next = items[index + 1];
      break;
    case 'ArrowLeft':
      if (expanded === 'true') current.click();
      else if (expanded === null) next = items.slice(0, index).findLast((item) => item.getAttribute('aria-level') === '1');
      break;
    default: return;
  }
  event.preventDefault();
  next?.focus();
}

interface TreeProps extends BrowserProps {
  schemas: CatalogSchema[];
  search: string;
}

function SchemaTree({ id, refreshedAt, unwrapCatalog, schemas, search }: TreeProps) {
  const { t } = useTranslation();
  const [openSchema, setOpenSchema] = useState<string | null>(null);
  const [collapsedMatches, setCollapsedMatches] = useState<string[]>([]);
  const [selected, setSelected] = useState<TableAddress | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const schemaFilter = search ? null : openSchema;
  const tables = useInfiniteQuery({
    queryKey: [...catalogKey(id), refreshedAt, 'tables', schemaFilter, search],
    enabled: Boolean(search || openSchema),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => unwrapCatalog(api.GET('/api/data-sources/{id}/catalog/tables', {
      params: {
        path: { id },
        query: { schema: schemaFilter ?? undefined, q: search || undefined, limit: 50, cursor: pageParam ?? undefined },
      },
      signal,
    })),
    getNextPageParam: (page) => page.nextCursor,
  });
  const bySchema = new Map<string, TableBrief[]>();
  for (const page of tables.data?.pages ?? []) {
    for (const table of page.items) {
      const group = bySchema.get(table.schema);
      if (group) group.push(table);
      else bySchema.set(table.schema, [table]);
    }
  }

  const names = search ? [...bySchema.keys()] : schemas.map((schema) => schema.name);
  const rows = names.flatMap((schema, schemaIndex) => {
    const expanded = search ? !collapsedMatches.includes(schema) : openSchema === schema;
    const children = expanded ? bySchema.get(schema) ?? [] : [];
    return [
      { schema, table: null, key: JSON.stringify([schema]), expanded, position: schemaIndex + 1, size: names.length },
      ...children.map((table, index) => ({
        schema, table, key: JSON.stringify([schema, table.name]), expanded: undefined, position: index + 1,
        size: tables.hasNextPage ? -1 : children.length,
      })),
    ];
  });
  const tabStop = rows.some((row) => row.key === focused) ? focused : rows[0]?.key;
  function toggleSchema(schema: string) {
    if (!search || selected?.schema === schema) setSelected(null);
    if (search) {
      setCollapsedMatches((previous) => previous.includes(schema)
        ? previous.filter((name) => name !== schema) : [...previous, schema]);
    } else {
      setOpenSchema(openSchema === schema ? null : schema);
    }
  }

  return (
    <div className="grid min-w-0 gap-5 md:grid-cols-[minmax(12rem,1fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-2">
        {rows.length > 0 && (
          <div role="tree" tabIndex={-1} aria-label={t('datasources.catalog.tree')} onKeyDown={navigateTree} className="space-y-1">
            {rows.map(({ schema, table, key, expanded, position, size }) => {
              const active = table !== null && selected?.schema === schema && selected.name === table.name;
              const Icon = table ? Table2 : expanded ? ChevronDown : ChevronRight;
              return (
                <button
                  key={key}
                  type="button"
                  role="treeitem"
                  aria-label={table?.name ?? schema}
                  title={table?.boundType ? t('datasources.catalog.boundType', { label: table.boundType.label }) : undefined}
                  aria-level={table ? 2 : 1}
                  aria-posinset={position}
                  aria-setsize={size}
                  aria-expanded={expanded}
                  aria-selected={table ? active : undefined}
                  tabIndex={key === tabStop ? 0 : -1}
                  className={cn(
                    'flex min-h-9 w-full flex-wrap items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-muted',
                    'focus-visible:outline-2 focus-visible:outline-ring',
                    table && 'pl-7',
                    active && 'bg-primary-soft text-primary-strong',
                  )}
                  onFocus={() => setFocused(key)}
                  onClick={() => table ? setSelected(table) : toggleSchema(schema)}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  <span className="break-all">{table?.name ?? schema}</span>
                  {table?.boundType && <Badge tone="primary" className="max-w-full truncate">{table.boundType.label}</Badge>}
                </button>
              );
            })}
          </div>
        )}
        {tables.isLoading && <LoadingState />}
        {tables.isError ? (
          <ErrorState error={tables.error} onRetry={() => {
            if (tables.isFetchNextPageError) void tables.fetchNextPage();
            else void tables.refetch();
          }} />
        ) : tables.hasNextPage && (
          <Button size="sm" variant="secondary" loading={tables.isFetching} onClick={() => void tables.fetchNextPage()}>
            {t('datasources.catalog.loadMore')}
          </Button>
        )}
        {tables.isSuccess && !bySchema.size && (
          <p className="text-sm text-muted-foreground">{t(search ? 'datasources.catalog.noMatches' : 'datasources.catalog.emptyTables')}</p>
        )}
      </div>
      <div className="min-w-0 border-t border-border pt-4 md:border-l md:border-t-0 md:pl-5 md:pt-0">
        {selected ? <TableDetail id={id} refreshedAt={refreshedAt} unwrapCatalog={unwrapCatalog} table={selected} /> : (
          <p className="text-sm text-muted-foreground">{t('datasources.catalog.selectTable')}</p>
        )}
      </div>
    </div>
  );
}

export function CatalogBrowser({ id, refreshedAt, unwrapCatalog }: BrowserProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(input.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [input]);
  const schemas = useQuery({
    queryKey: [...catalogKey(id), refreshedAt, 'schemas'],
    queryFn: ({ signal }) => unwrapCatalog(api.GET('/api/data-sources/{id}/catalog/schemas', { params: { path: { id } }, signal })),
  });
  return (
    <QueryState query={schemas} requiredRole="editor">
      {(data) => data.length ? (
        <div className="space-y-4">
          <Input type="search" aria-label={t('datasources.catalog.search')} placeholder={t('datasources.catalog.search')}
            className="max-w-sm" value={input} maxLength={128} onChange={(event) => setInput(event.target.value)} />
          <SchemaTree key={search} schemas={data} id={id} refreshedAt={refreshedAt} search={search} unwrapCatalog={unwrapCatalog} />
        </div>
      ) : <p className="text-sm text-muted-foreground">{t('datasources.catalog.emptySchemas')}</p>}
    </QueryState>
  );
}

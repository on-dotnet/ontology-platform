import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import type { Datatype } from '@/features/ontologies/api';

export type TypeBindingView = components['schemas']['TypeBindingView'];
export type TableBindingView = components['schemas']['TableBindingView'];
export type PropertyBindingView = components['schemas']['PropertyBindingView'];
export type RelationBindingView = components['schemas']['RelationBindingView'];
export type JoinBindingView = components['schemas']['JoinBindingView'];
export type CatalogCheck = TableBindingView['check'];
export type TableBinding = components['schemas']['TableBinding'];
export type ColumnBinding = components['schemas']['ColumnBinding'];
export type JoinBinding = components['schemas']['JoinBinding'];
export type BindingValue = TableBinding | ColumnBinding | JoinBinding;
export type Join = JoinBinding['join'];
export type DataSource = components['schemas']['DataSource'];
export type CatalogTableBrief = components['schemas']['CatalogTableBrief'];
export type CatalogTable = components['schemas']['CatalogTable'];
export type CatalogColumn = components['schemas']['CatalogColumn'];
export type ColumnFamily = CatalogColumn['family'];

export const bindingKeys = {
  all: ['bindings'] as const,
  views: (ontologyId: string, typeId?: string) => [...bindingKeys.all, 'views', ontologyId, typeId ?? ''] as const,
  dataSources: () => [...bindingKeys.all, 'data-sources'] as const,
  tables: (dataSourceId: string, q: string) => [...bindingKeys.all, 'tables', dataSourceId, q] as const,
  table: (dataSourceId: string, schema: string, table: string) => [...bindingKeys.all, 'table', dataSourceId, schema, table] as const,
};

/**
 * The working version's bindings, organised by object type and checked against the catalog cache.
 * With `typeId` the list holds that one type (bound or not); without it, every bound type.
 */
export function useBindingViews(ontologyId: string, typeId?: string) {
  return useQuery({
    queryKey: bindingKeys.views(ontologyId, typeId),
    queryFn: () =>
      unwrap(api.GET('/api/ontologies/{id}/bindings', { params: { path: { id: ontologyId }, query: typeId ? { typeId } : {} } })),
  });
}

/** Data sources a type may be bound to (archived ones are left out of the choice). */
export function useDataSources(enabled = true) {
  return useQuery({
    queryKey: bindingKeys.dataSources(),
    queryFn: () => unwrap(api.GET('/api/data-sources')),
    enabled,
  });
}

/** Tables and views of a data source's catalog cache, searched by name. */
export function useCatalogTables(dataSourceId: string | undefined, q: string) {
  return useQuery({
    queryKey: bindingKeys.tables(dataSourceId ?? '', q),
    queryFn: () =>
      unwrap(
        api.GET('/api/data-sources/{id}/catalog/tables', {
          params: { path: { id: dataSourceId ?? '' }, query: q ? { q, limit: 50 } : { limit: 50 } },
        }),
      ),
    enabled: Boolean(dataSourceId),
  });
}

/** Columns, primary key and foreign keys of one table in the catalog cache. */
export function useCatalogTable(dataSourceId: string | undefined, schema: string | undefined, table: string | undefined) {
  return useQuery({
    queryKey: bindingKeys.table(dataSourceId ?? '', schema ?? '', table ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/api/data-sources/{id}/catalog/tables/{schema}/{table}', {
          params: { path: { id: dataSourceId ?? '', schema: schema ?? '', table: table ?? '' } },
        }),
      ),
    enabled: Boolean(dataSourceId && schema && table),
  });
}

/**
 * Column families a property of each datatype may be bound to; the server checks the same table
 * (`binding_rules.FAMILIES`) and answers `binding.type_mismatch` otherwise.
 */
export const COMPATIBLE_FAMILIES: Record<Datatype, readonly ColumnFamily[]> = {
  string: ['string', 'opaque'],
  integer: ['integer'],
  decimal: ['integer', 'decimal'],
  boolean: ['boolean'],
  date: ['date'],
  dateTime: ['date', 'dateTime'],
};

/** Whether a column may hold a property of this datatype; properties without one bind to nothing. */
export function columnFits(datatype: Datatype | null, column: Pick<CatalogColumn, 'family'>): boolean {
  return datatype !== null && COMPATIBLE_FAMILIES[datatype].includes(column.family);
}

/** Families that cannot identify a row (json, arrays, …): not offered as key columns. */
export function canBeKey(column: Pick<CatalogColumn, 'family'>): boolean {
  return column.family !== 'other';
}

/** "schema.table", as tables are written everywhere in the binding UI. */
export function tableName(schema: string, table: string): string {
  return `${schema}.${table}`;
}

/** Later pages use the server's opaque cursor and the same search as the first page. */
export function useNextCatalogPage(dataSourceId: string, q: string, cursor: string | undefined) {
  return useQuery({
    queryKey: [...bindingKeys.tables(dataSourceId, q), cursor],
    queryFn: () =>
      unwrap(api.GET('/api/data-sources/{id}/catalog/tables', {
        params: { path: { id: dataSourceId }, query: { q: q || undefined, cursor, limit: 50 } },
      })),
    enabled: Boolean(cursor),
  });
}

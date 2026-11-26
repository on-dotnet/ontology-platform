import { ArrowDown, ArrowUp, ArrowUpDown, Rows3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { EmptyState } from '@/components/states/empty-state';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { useSearch } from './api';
import { FilterEditor } from './filter-editor';
import { keyLabel, PropertyValue } from './object-values';
import { QueryResult } from './query-result';

type Row = components['schemas']['ObjectRow'];
type Sort = components['schemas']['Sort'];
type Filter = components['schemas']['Filter'];
type ObjectType = components['schemas']['ObjectTypeInfo'];

export interface Criteria {
  filters: Filter[];
  sort: Sort[];
}

function toggleSort(sort: Sort[], propertyId: string): Sort[] {
  const existing = sort.find((entry) => entry.propertyId === propertyId);
  if (!existing) return [...sort.slice(0, 1), { propertyId, direction: 'asc' }];
  if (existing.direction === 'desc') return sort.filter((entry) => entry !== existing);
  return sort.map((entry) => entry === existing ? { propertyId, direction: 'desc' } : entry);
}

interface ObjectTableProps {
  id: string;
  releaseId: string;
  type: ObjectType;
  criteria: Criteria;
  onChange: (criteria: Criteria) => void;
  onOpen: (row: Row) => void;
  onRestart: () => void;
  cursor: string | null;
  onPage: (cursor: string | null) => void;
}

export function ObjectTable({ id, releaseId, type, criteria, onChange, onOpen, onRestart, cursor, onPage }: ObjectTableProps) {
  const { t } = useTranslation();
  const { filters, sort } = criteria;
  const query = useSearch(id, releaseId, { typeId: type.typeId, filters, sort, cursor, limit: 50 });
  function change(next: Criteria) {
    onPage(null);
    onChange(next);
  }
  return (
    <div className="space-y-4">
      <FilterEditor properties={type.properties} filters={filters} onChange={(next) => change({ filters: next, sort })} />
      <QueryResult query={query} id={id} onRestart={onRestart} onFirstPage={cursor !== null ? () => onPage(null) : undefined}>
        {(page) => (
          <>
            {page.items.length ? (
              <div className="max-h-96 overflow-auto rounded-lg border border-border">
                <Table aria-label={type.label}>
                  <TableHeader><TableRow>
                    <TableHead>{t('explore.primaryKey')}</TableHead>
                    {type.properties.map((property) => {
                      const index = sort.findIndex((entry) => entry.propertyId === property.propertyId);
                      const direction = sort[index]?.direction;
                      const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
                      return (
                        <TableHead key={property.propertyId} numeric={property.datatype === 'integer' || property.datatype === 'decimal'}
                          aria-sort={index === 0 ? (direction === 'asc' ? 'ascending' : 'descending') : undefined}>
                          <button type="button" className="inline-flex cursor-pointer items-center gap-1 rounded hover:text-primary-strong"
                            onClick={() => change({ filters, sort: toggleSort(sort, property.propertyId) })}>
                            {property.label}{property.unit && <span>({property.unit})</span>}
                            <Icon aria-hidden className="size-3.5" />
                            {direction && <>
                              <span aria-hidden>{index + 1}</span>
                              <span className="sr-only">{t(`explore.sort.${direction}`, { position: index + 1 })}</span>
                            </>}
                          </button>
                        </TableHead>
                      );
                    })}
                  </TableRow></TableHeader>
                  <TableBody>
                    {page.items.map((row) => (
                      <TableRow key={row.key} className="cursor-pointer" onClick={(event) => {
                        if (event.target instanceof Element && !event.target.closest('button')) onOpen(row);
                      }}>
                        <TableCell>
                          <button type="button" className="cursor-pointer rounded text-left font-medium text-primary-strong hover:underline"
                            onClick={() => onOpen(row)}>{keyLabel(row)}</button>
                        </TableCell>
                        {type.properties.map((property) => (
                          <TableCell key={property.propertyId} numeric={property.datatype === 'integer' || property.datatype === 'decimal'} className="break-words">
                            <PropertyValue property={property} row={row} />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <EmptyState icon={Rows3} title={t(filters.length ? 'explore.noMatches' : 'explore.noRows')}
                action={filters.length > 0 && <Button onClick={() => change({ filters: [], sort })}>{t('explore.clearFilters')}</Button>} />
            )}
            {(cursor !== null || page.nextCursor !== null) && (
              <div className="flex flex-wrap justify-end gap-2">
                {cursor !== null && <Button size="sm" variant="ghost" onClick={() => onPage(null)}>{t('explore.firstPage')}</Button>}
                {page.nextCursor !== null && <Button size="sm" variant="secondary" onClick={() => onPage(page.nextCursor)}>{t('explore.nextPage')}</Button>}
              </div>
            )}
          </>
        )}
      </QueryResult>
    </div>
  );
}

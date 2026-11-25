import { RotateCcw, Search, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { usePermissions } from '@/features/auth/permissions';
import {
  displayName,
  ELEMENT_KINDS,
  elementName,
  turtleSummary,
  useElements,
  type Element,
  type ElementKind,
  type ElementStatusFilter,
} from '@/features/ontologies/api';
import { cn } from '@/lib/cn';
import { usePagination } from '@/lib/pagination';

import { useRestoreElement } from './edit-actions';

/** Search waits this long after the last keystroke. */
export const SEARCH_DEBOUNCE_MS = 300;

export const kindTone: Record<ElementKind, BadgeTone> = {
  entity_type: 'primary',
  relation_type: 'secondary',
  property: 'success',
  constraint: 'neutral',
  axiom: 'neutral',
  type_binding: 'neutral',
  property_binding: 'neutral',
  relation_binding: 'neutral',
};

type KindFilter = ElementKind | 'all';
const STATUS_FILTERS: readonly ElementStatusFilter[] = ['active', 'deprecated', 'all'];

interface ElementListProps {
  ontologyId: string;
  onSelect: (elementId: string) => void;
}

/** Elements filtered by kind and status and searched by name or synonym (server side); deleted ones can be restored. */
export function ElementList({ ontologyId, onSelect }: ElementListProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const { canUpload } = usePermissions();
  const [kind, setKind] = useState<KindFilter>('all');
  // In-use elements by default, like the server.
  const [status, setStatus] = useState<ElementStatusFilter>('active');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const query = useElements(ontologyId, { ...(kind === 'all' ? {} : { kind }), ...(q ? { q } : {}), ...(status === 'active' ? {} : { status }) });
  // Names of the types constraints target and of the elements axioms belong to, deleted ones included.
  const everything = useElements(ontologyId, { status: 'all' });
  const { restore, pendingId, apply: restoresAtOnce } = useRestoreElement(ontologyId);
  const byId = new Map((everything.data ?? []).map((element) => [element.id, element]));
  const nameOf = (id: string | null) => {
    if (!everything.isSuccess) return null;
    const element = id ? byId.get(id) : undefined;
    return element ? elementName(element, language) : undefined;
  };
  // Only axioms while axioms are listed, also while the rows of the previous filter stay on screen.
  const shown = (query.data ?? []).filter((element) => kind !== 'axiom' || element.kind === 'axiom');
  const pager = usePagination(shown.length, `${kind}|${q}|${status}`);
  const cardRef = useRef<HTMLDivElement>(null);
  const filtered = kind !== 'all' || q !== '' || status !== 'active';
  // Only deleted rows have an action: restoring them.
  const showActions = canUpload && status !== 'active';
  const statusLabel = (value: ElementStatusFilter) => t(`ontologyPage.list.status.${value}`);
  const groupId = useId();
  const columnCount = showActions ? 5 : 4;

  const clearSearch = () => {
    setText('');
    setQ('');
  };

  /** A table row; axioms listed under their subject leave the subject out of the row. */
  const renderRow = (element: Element, grouped: boolean) => (
    <TableRow key={element.id}>
      <TableCell className="max-w-64">
        <NameCell element={element} language={language} nameOf={nameOf} showSubject={!grouped} onSelect={onSelect} />
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={kindTone[element.kind]}>{t(`kind.${element.kind}`)}</Badge>
          {element.status === 'deprecated' ? <Badge tone="warning">{t('ontologyPage.detail.deprecated')}</Badge> : null}
        </div>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">{element.localName ?? '—'}</TableCell>
      <TableCell className="max-w-md">
        <p className="line-clamp-2 text-muted-foreground">{element.definitionZh ?? element.definitionEn ?? '—'}</p>
      </TableCell>
      {showActions ? (
        <TableCell className="whitespace-nowrap">
          {element.status === 'deprecated' ? (
            <Button
              variant="secondary"
              size="sm"
              aria-label={t(restoresAtOnce ? 'ontologyPage.list.restoreElement' : 'ontologyPage.list.submitRestoreElement', {
                name: elementName(element, language) || t('kind.axiom'),
              })}
              loading={pendingId === element.id}
              disabled={pendingId !== undefined && pendingId !== element.id}
              onClick={() => restore(element)}
            >
              <RotateCcw aria-hidden />
              {restoresAtOnce ? t('ontologyPage.edit.restore') : t('ontologyPage.edit.submitRestore')}
            </Button>
          ) : null}
        </TableCell>
      ) : null}
    </TableRow>
  );

  return (
    <Card ref={cardRef}>
      <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
        <SegmentedControl
          legend={t('ontologyPage.list.kindFilter')}
          hideLegend
          value={kind}
          onValueChange={setKind}
          options={[
            { value: 'all', label: t('ontologyPage.list.allKinds') },
            ...ELEMENT_KINDS.map((value) => ({ value, label: t(`kinds.${value}`) })),
          ]}
        />
        <SegmentedControl
          legend={t('ontologyPage.list.statusFilter')}
          hideLegend
          value={status}
          onValueChange={setStatus}
          options={STATUS_FILTERS.map((value) => ({ value, label: statusLabel(value) }))}
        />
        <div className="relative ml-auto w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-label={t('ontologyPage.list.search')}
            placeholder={t('ontologyPage.list.searchPlaceholder')}
            className="h-9 pl-9"
          />
        </div>
        {filtered ? (
          <ul className="flex w-full flex-wrap gap-2" aria-label={t('ontologyPage.list.activeFilters')}>
            {kind !== 'all' ? (
              <li>
                <FilterChip label={t('ontologyPage.list.kindChip', { kind: t(`kinds.${kind}`) })} onRemove={() => setKind('all')} />
              </li>
            ) : null}
            {status !== 'active' ? (
              <li>
                <FilterChip label={t('ontologyPage.list.statusChip', { status: statusLabel(status) })} onRemove={() => setStatus('active')} />
              </li>
            ) : null}
            {q ? (
              <li>
                <FilterChip label={t('ontologyPage.list.searchChip', { q })} onRemove={clearSearch} />
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>

      <QueryState query={query}>
        {(elements) =>
          elements.length === 0 ? (
            <EmptyState
              icon={Search}
              tone="secondary"
              title={filtered ? t('ontologyPage.list.noMatchTitle') : t('ontologyPage.list.emptyTitle')}
              description={filtered ? t('ontologyPage.list.noMatchDescription') : t('ontologyPage.list.emptyDescription')}
            />
          ) : (
            <>
            <Table aria-label={t('ontologyPage.list.tableLabel')}>
              <TableHeader>
                <TableRow className="border-t-0 hover:bg-transparent">
                  <TableHead>{t('ontologyPage.list.columns.name')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.kind')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.localName')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.definition')}</TableHead>
                  {showActions ? <TableHead className="w-px whitespace-nowrap">{t('ontologyPage.list.columns.actions')}</TableHead> : null}
                </TableRow>
              </TableHeader>
              {kind === 'axiom' ? (
                pageGroups(axiomGroups(shown, nameOf, language), pager.start, pager.end).map((group, index) => {
                  const labelId = `${groupId}-${index}`;
                  return (
                    <TableBody key={group.subjectId ?? ''} aria-labelledby={labelId}>
                      <tr className="border-t border-border bg-background">
                        <th scope="rowgroup" colSpan={columnCount} className="h-9 px-4 text-left text-xs font-semibold text-muted-foreground">
                          <span className="inline-flex items-center gap-2">
                            <span id={labelId} className="text-foreground">
                              {group.subjectId === null ? (
                                t('ontologyPage.list.noSubject')
                              ) : group.name === null ? (
                                <Skeleton className="inline-block h-3.5 w-20 align-middle" />
                              ) : (
                                (group.name ?? t('ontologyPage.detail.unknownElement'))
                              )}
                            </span>
                            <span className="font-normal tabular-nums">{t('ontologyPage.list.groupCount', { count: group.total })}</span>
                          </span>
                        </th>
                      </tr>
                      {group.axioms.map((element) => renderRow(element, true))}
                    </TableBody>
                  );
                })
              ) : (
                <TableBody>{shown.slice(pager.start, pager.end).map((element) => renderRow(element, false))}</TableBody>
              )}
            </Table>
            <Pagination state={pager} total={shown.length} onChange={() => cardRef.current?.scrollIntoView({ block: 'start' })} />
            </>
          )
        }
      </QueryState>
    </Card>
  );
}

export interface AxiomGroup {
  /** The element the axioms belong to; null for axioms whose subject is no element (ontology annotations, SKOS terms…). */
  subjectId: string | null;
  /** The subject's name; undefined when it is unknown, null until the names have loaded. */
  name: string | null | undefined;
  axioms: Element[];
}

/**
 * Axioms grouped by the element they belong to, groups in name order; axioms about no element
 * (ontology annotations, terms of other vocabularies) come last. Axioms keep the server's order within a group.
 */
export function axiomGroups(axioms: readonly Element[], nameOf: (id: string | null) => string | null | undefined, language: string): AxiomGroup[] {
  const groups = new Map<string | null, AxiomGroup>();
  for (const axiom of axioms) {
    const key = axiom.subjectId ?? null;
    const group = groups.get(key) ?? { subjectId: key, name: key === null ? undefined : nameOf(key), axioms: [] };
    group.axioms.push(axiom);
    groups.set(key, group);
  }
  const collator = new Intl.Collator(language);
  return [...groups.values()].sort((a, b) => {
    if (a.subjectId === null || b.subjectId === null) return a.subjectId === null ? 1 : -1;
    return collator.compare(a.name ?? '', b.name ?? '');
  });
}

export interface PagedAxiomGroup extends AxiomGroup {
  /** All axioms of the group, of which `axioms` holds those on the page. */
  total: number;
}

/** The part of the groups, read in order, that falls on the rows `start` to `end` (exclusive); groups left empty are dropped. */
export function pageGroups(groups: readonly AxiomGroup[], start: number, end: number): PagedAxiomGroup[] {
  const paged: PagedAxiomGroup[] = [];
  let offset = 0;
  for (const group of groups) {
    const axioms = group.axioms.slice(Math.max(start - offset, 0), Math.max(end - offset, 0));
    offset += group.axioms.length;
    if (axioms.length > 0) paged.push({ ...group, axioms, total: group.axioms.length });
  }
  return paged;
}

interface NameCellProps {
  element: Element;
  language: string;
  /** The element's name; undefined for an unknown element, null until the names have loaded. */
  nameOf: (id: string | null) => string | null | undefined;
  /** Axioms name the element they belong to, unless they are listed under it. */
  showSubject: boolean;
  onSelect: (elementId: string) => void;
}

/** Name and second line: axioms show their Turtle; constraints their target type; others the English name. */
function NameCell({ element, language, nameOf, showSubject, onSelect }: NameCellProps) {
  const { t } = useTranslation();
  const isAxiom = element.kind === 'axiom';
  const name = isAxiom ? turtleSummary(element.turtle) : displayName(element, language);
  let detail: string | null = null;
  if (element.kind === 'constraint') {
    const target = nameOf(element.domainId);
    // Nothing while names load: "unknown type" would be wrong for a moment.
    detail = target === null ? null : t('ontologyPage.list.target', { name: target ?? t('review.unknownType') });
  } else if (isAxiom && showSubject) {
    const subject = nameOf(element.subjectId);
    detail = subject ? t('ontologyPage.list.subject', { name: subject }) : null;
  } else if (element.labelEn && !language.startsWith('en') && element.labelEn !== name) {
    detail = element.labelEn;
  }
  return (
    <>
      <button
        type="button"
        onClick={() => onSelect(element.id)}
        className={cn(
          'block max-w-full truncate rounded text-left font-medium text-primary-strong hover:underline',
          isAxiom && 'font-mono text-xs',
        )}
      >
        {name || '—'}
      </button>
      {detail ? <p className="truncate text-xs text-muted-foreground">{detail}</p> : null}
    </>
  );
}

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex h-7 items-center gap-1 rounded-md bg-primary-soft pl-2.5 pr-1 text-xs font-medium text-primary-strong">
      {label}
      <Tooltip content={t('ontologyPage.list.removeFilter', { label })}>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-5 text-primary-strong hover:bg-primary/15 hover:text-primary-strong"
          aria-label={t('ontologyPage.list.removeFilter', { label })}
          onClick={onRemove}
        >
          <X className="size-3.5" aria-hidden />
        </Button>
      </Tooltip>
    </span>
  );
}

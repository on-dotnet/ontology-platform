import { Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { displayName, ELEMENT_KINDS, elementName, turtleSummary, useElements, type Element, type ElementKind } from '@/features/ontologies/api';
import { cn } from '@/lib/cn';

/** Search waits this long after the last keystroke. */
export const SEARCH_DEBOUNCE_MS = 300;

export const kindTone: Record<ElementKind, BadgeTone> = {
  entity_type: 'primary',
  relation_type: 'secondary',
  property: 'success',
  constraint: 'neutral',
  axiom: 'neutral',
};

type KindFilter = ElementKind | 'all';

interface ElementListProps {
  ontologyId: string;
  onSelect: (elementId: string) => void;
}

/** Elements filtered by kind and searched by name or synonym (server side). */
export function ElementList({ ontologyId, onSelect }: ElementListProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const [kind, setKind] = useState<KindFilter>('all');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const query = useElements(ontologyId, { ...(kind === 'all' ? {} : { kind }), ...(q ? { q } : {}) });
  // Names of the types constraints target and of the elements axioms belong to.
  const everything = useElements(ontologyId);
  const byId = new Map((everything.data ?? []).map((element) => [element.id, element]));
  const nameOf = (id: string | null) => {
    if (!everything.isSuccess) return null;
    const element = id ? byId.get(id) : undefined;
    return element ? elementName(element, language) : undefined;
  };
  const filtered = kind !== 'all' || q !== '';

  const clearSearch = () => {
    setText('');
    setQ('');
  };

  return (
    <Card>
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
            <Table aria-label={t('ontologyPage.list.tableLabel')}>
              <TableHeader>
                <TableRow className="border-t-0 hover:bg-transparent">
                  <TableHead>{t('ontologyPage.list.columns.name')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.kind')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.localName')}</TableHead>
                  <TableHead>{t('ontologyPage.list.columns.definition')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {elements.map((element) => (
                  <TableRow key={element.id}>
                    <TableCell className="max-w-64">
                      <NameCell element={element} language={language} nameOf={nameOf} onSelect={onSelect} />
                    </TableCell>
                    <TableCell>
                      <Badge tone={kindTone[element.kind]}>{t(`kind.${element.kind}`)}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{element.localName ?? '—'}</TableCell>
                    <TableCell className="max-w-md">
                      <p className="line-clamp-2 text-muted-foreground">{element.definitionZh ?? element.definitionEn ?? '—'}</p>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )
        }
      </QueryState>
    </Card>
  );
}

interface NameCellProps {
  element: Element;
  language: string;
  /** The element's name; undefined for an unknown element, null until the names have loaded. */
  nameOf: (id: string | null) => string | null | undefined;
  onSelect: (elementId: string) => void;
}

/** Name and second line: axioms show their Turtle; constraints their target type; others the English name. */
function NameCell({ element, language, nameOf, onSelect }: NameCellProps) {
  const { t } = useTranslation();
  const isAxiom = element.kind === 'axiom';
  const name = isAxiom ? turtleSummary(element.turtle) : displayName(element, language);
  let detail: string | null = null;
  if (element.kind === 'constraint') {
    const target = nameOf(element.domainId);
    // Nothing while names load: "unknown type" would be wrong for a moment.
    detail = target === null ? null : t('ontologyPage.list.target', { name: target ?? t('review.unknownType') });
  } else if (isAxiom) {
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

import { ChevronRight, Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Pagination } from '@/components/ui/pagination';
import { usePagination } from '@/lib/pagination';

import { ObjectDetailPanel } from './object-detail';
import { ObjectTable, type Criteria } from './object-table';
import { keyLabel } from './object-values';

type ObjectType = components['schemas']['ObjectTypeInfo'];
type Row = components['schemas']['ObjectRow'];

export function TypeList({ types, selected, onSelect }: { types: ObjectType[]; selected?: string; onSelect: (id: string) => void }) {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const needle = search.trim().toLocaleLowerCase(i18n.language);
  const matching = types.filter((type) => type.label.toLocaleLowerCase(i18n.language).includes(needle));
  const pages = usePagination(matching.length, needle);
  return (
    <Card className="min-w-0 self-start p-5 lg:col-span-1">
      <h2 className="mb-3 text-base font-semibold">{t('explore.types')}</h2>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input type="search" value={search} onChange={(event) => setSearch(event.target.value)}
          aria-label={t('explore.searchTypes')} placeholder={t('explore.searchTypes')} className="pl-9" />
      </div>
      {matching.length ? (
        <ul className="mt-3 space-y-1" aria-label={t('explore.types')}>
          {matching.slice(pages.start, pages.end).map((type) => (
            <li key={type.typeId} className="min-w-0">
              <Button variant={selected === type.typeId ? 'soft' : 'ghost'}
                className="h-auto min-h-10 w-full justify-start whitespace-normal break-words text-left"
                disabled={type.problem !== null} aria-pressed={selected === type.typeId}
                aria-describedby={type.problem ? `reason-${type.typeId}` : undefined}
                onClick={() => onSelect(type.typeId)}>{type.label}</Button>
              {type.problem && <p id={`reason-${type.typeId}`} className="px-3 pb-2 text-xs text-warning-strong">
                {t(`explore.problem.${type.problem}`)}
              </p>}
            </li>
          ))}
        </ul>
      ) : <p className="mt-4 text-sm text-muted-foreground">{t('explore.noTypesMatch')}</p>}
      <Pagination total={matching.length} state={pages} />
    </Card>
  );
}

interface TypeBrowserProps {
  id: string;
  releaseId: string;
  type: ObjectType;
  types: ObjectType[];
  criteria: Criteria;
  onChange: (criteria: Criteria) => void;
  onRestart: () => void;
}

export function TypeBrowser({ id, releaseId, type, types, criteria, onChange, onRestart }: TypeBrowserProps) {
  const { t } = useTranslation();
  const [trail, setTrail] = useState<Row[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const current = trail.at(-1);
  const heading = useRef<HTMLHeadingElement>(null);
  const moveFocus = useRef(false);
  function navigate(path: Row[]) {
    moveFocus.current = true;
    setTrail(path);
  }
  useEffect(() => {
    if (moveFocus.current) heading.current?.focus();
    moveFocus.current = false;
  }, [trail]);
  const open = (row: Row) => navigate([...trail, row]);

  return (
    <Card className="min-w-0 space-y-4 p-5 lg:col-span-3">
      {current && (
        <nav aria-label={t('explore.trail')}>
          <ol className="flex flex-wrap items-center gap-1 text-sm">
            <li><Button size="sm" variant="ghost" onClick={() => navigate([])}>{type.label}</Button></li>
            {trail.map((row, index) => (
              <li key={index} className="flex min-w-0 items-center gap-1">
                <ChevronRight aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                {index === trail.length - 1 ? <span aria-current="page" className="break-all font-medium">{keyLabel(row)}</span>
                  : <Button size="sm" variant="ghost" onClick={() => navigate(trail.slice(0, index + 1))}>{keyLabel(row)}</Button>}
              </li>
            ))}
          </ol>
        </nav>
      )}
      <h2 ref={heading} tabIndex={-1} className="break-words text-lg font-semibold">
        {current ? t('explore.detailTitle', { type: types.find((item) => item.typeId === current.typeId)?.label, key: keyLabel(current) }) : type.label}
      </h2>
      {current ? (
        <ObjectDetailPanel key={`${current.typeId}:${current.key}:${trail.length}`}
          id={id} releaseId={releaseId} row={current} types={types} onOpen={open} onRestart={onRestart} />
      ) : (
        <ObjectTable id={id} releaseId={releaseId} type={type} criteria={criteria} onChange={onChange}
          onOpen={open} onRestart={onRestart} cursor={cursor} onPage={setCursor} />
      )}
    </Card>
  );
}

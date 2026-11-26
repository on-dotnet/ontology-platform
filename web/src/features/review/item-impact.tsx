import { useTranslation } from 'react-i18next';

import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { elementName, useImpact, type ElementRef, type Impact } from '@/features/ontologies/api';
import { CascadeList } from '@/features/ontology/element-impact';
import { kindTone } from '@/features/ontology/element-list';
import { directMetricRefs } from '@/features/ontology/metric-definition';
import { cn } from '@/lib/cn';

import type { ChangeItem } from './api';
import type { RefContext } from './item-fields';

/** Elements that refer to the target directly, each once. */
function directRefs(impact: Impact, context: RefContext): ElementRef[] {
  const refs = [...impact.subtypes, ...impact.relations, ...impact.properties, ...impact.constraints, ...impact.axioms,
    ...directMetricRefs(impact, context.elementsById)];
  if (impact.inverse) refs.push(impact.inverse);
  return [...new Map(refs.map((ref) => [ref.id, ref])).values()];
}

interface ItemImpactProps {
  ontologyId: string;
  /** An update or delete of an existing element. */
  item: ChangeItem & { targetElementId: string };
  context: RefContext;
}

/**
 * Impact summary of an update or delete item, loaded when opened: a delete lists everything it
 * takes along; an update, the elements that refer to the element it changes.
 */
export function ItemImpact({ ontologyId, item, context }: ItemImpactProps) {
  const { t } = useTranslation();
  const impact = useImpact(ontologyId, item.targetElementId);
  const nameOf = (ref: ElementRef) => {
    const element = context.elementsById.get(ref.id);
    return (element ? elementName(element, context.language) : '') || ref.label || '—';
  };
  return (
    <QueryState query={impact} loading={<Skeleton className="h-16 rounded-lg" />}>
      {(data) => {
        if (item.op === 'delete') return <CascadeList cascade={data.cascade} nameOf={nameOf} />;
        const refs = directRefs(data, context);
        if (refs.length === 0) return <p className="text-sm text-muted-foreground">{t('review.impact.none')}</p>;
        const label = t('review.impact.referencedBy', { count: refs.length });
        return (
          <section className="space-y-2">
            <h4 className="text-sm font-semibold text-foreground">{label}</h4>
            <ul className="divide-y divide-border rounded-lg border border-border" aria-label={label}>
              {refs.map((ref) => (
                <li key={ref.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-sm">
                  <Badge tone={kindTone[ref.kind]}>{t(`kind.${ref.kind}`)}</Badge>
                  <span className={cn('min-w-0 flex-1 truncate text-foreground', ref.kind === 'axiom' && 'font-mono text-xs')}>{nameOf(ref)}</span>
                </li>
              ))}
            </ul>
          </section>
        );
      }}
    </QueryState>
  );
}

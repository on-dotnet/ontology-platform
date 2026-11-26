import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { Element, ElementFields, ElementRef, Impact } from '@/features/ontologies/api';

export type Metric = NonNullable<Element['metric']>;
type MetricFields = NonNullable<ElementFields['metric']>;

export function directMetricRefs(impact: Impact, elementsById: ReadonlyMap<string, Element>): ElementRef[] {
  const target = impact.elementId;
  // A deletion cascade can reach metrics indirectly. Only their own references belong in this list.
  return impact.cascade.flatMap(({ element }) => {
    if (element.kind !== 'metric') return [];
    const metric = elementsById.get(element.id);
    if (metric?.kind !== 'metric' || metric.status !== 'active') return [];
    const definition = metric.metric;
    const direct = metric.subjectId === target || definition?.propertyId === target ||
      definition?.filters.some((condition) => condition.propertyId === target) ||
      definition?.numerator.some((condition) => condition.propertyId === target);
    return direct ? [element] : [];
  });
}

export function metricFields(metric: Metric): MetricFields {
  const withRefs = (filters: Metric['filters']) => filters.map(({ propertyId, ...condition }) => ({ propertyRef: propertyId, ...condition }));
  return {
    aggregate: metric.aggregate,
    propertyRef: metric.propertyId,
    filters: withRefs(metric.filters),
    numerator: withRefs(metric.numerator),
    decimals: metric.decimals,
    percent: metric.percent,
  };
}

interface MetricDefinitionProps {
  fields: Pick<ElementFields, 'subjectRef' | 'metric' | 'unit'>;
  nameOf: (ref: string) => string | undefined;
  linkTo?: (ref: string) => ReactNode;
  onlyPresent?: boolean;
}

export function MetricDefinition({ fields, nameOf, linkTo, onlyPresent = false }: MetricDefinitionProps) {
  const { t, i18n } = useTranslation();
  const definition = fields.metric;
  const unknown = t('review.unknownElement');
  const name = (ref: string) => nameOf(ref) ?? unknown;
  const reference = (ref: string) => linkTo ? linkTo(ref) : name(ref);
  const row = (label: string, content: ReactNode) => (
    <div className="contents">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{content}</dd>
    </div>
  );
  const scalar = (value: string | number | boolean) => typeof value === 'boolean' ? t(value ? 'review.yes' : 'review.no') : String(value);
  const conditions = (filters: MetricFields['filters']) => filters?.length ? (
    <ul className="space-y-1">
      {filters.map(({ propertyRef, op, value }, index) => {
        const text = Array.isArray(value)
          ? new Intl.ListFormat(i18n.language, { type: 'disjunction' }).format(value.map(scalar))
          : value === undefined || value === null ? '' : scalar(value);
        return <li key={index}>{[name(propertyRef), t(`explore.op.${op}`), text].filter(Boolean).join(' ')}</li>;
      })}
    </ul>
  ) : t('ontologyPage.detail.none');

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      {(!onlyPresent || 'subjectRef' in fields) && row(t('ontologyMetric.subject'), fields.subjectRef ? reference(fields.subjectRef) : unknown)}
      {definition ? <>
        {row(t('ontologyMetric.aggregate'), t(`ontologyMetric.aggregates.${definition.aggregate}`))}
        {definition.propertyRef && row(t('ontologyMetric.property'), reference(definition.propertyRef))}
        {row(t('ontologyMetric.filters'), conditions(definition.filters))}
        {definition.aggregate === 'ratio' && row(t('ontologyMetric.numerator'), conditions(definition.numerator))}
        {row(t('ontologyMetric.decimals'), definition.decimals ?? 2)}
        {definition.aggregate === 'ratio' && row(t('ontologyMetric.percent'), t(definition.percent ? 'review.yes' : 'review.no'))}
      </> : (!onlyPresent || 'metric' in fields) && row(t('ontologyMetric.definition'), t('ontologyMetric.missing'))}
      {(!onlyPresent || 'unit' in fields) && row(t('review.fields.unit'), fields.unit || t('review.emptyValue'))}
    </dl>
  );
}

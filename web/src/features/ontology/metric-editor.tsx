import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { FilterEditor } from '@/features/explore/filter-editor';
import { elementName, type Element } from '@/features/ontologies/api';

import type { FormErrors } from './element-form';
import type { Metric } from './metric-definition';

type Property = components['schemas']['ObjectProperty'];
const aggregates: readonly Metric['aggregate'][] = ['count', 'sum', 'avg', 'min', 'max', 'ratio'];

function filterOps(datatype: Property['datatype']): Property['ops'] {
  if (datatype === 'boolean') return ['eq', 'ne', 'isNull', 'notNull'];
  const ops: Property['ops'] = ['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in', 'isNull', 'notNull'];
  if (datatype === 'string') ops.push('contains', 'startsWith');
  return ops;
}

export function metricProperties(elements: readonly Element[], subject: string, language: string): Property[] {
  return elements.flatMap((element) => {
    if (element.kind !== 'property' || !element.datatype) return [];
    // Keep old names readable while a change of subject makes the user replace its conditions.
    const available = element.domainId === subject && element.status === 'active';
    return [{
      propertyId: element.id, label: elementName(element, language), datatype: element.datatype,
      unit: element.unit, ops: available ? filterOps(element.datatype) : [],
    }];
  });
}

function acceptsProperty(aggregate: Metric['aggregate'], property: Property) {
  if (!property.ops.length || aggregate === 'count' || aggregate === 'ratio') return false;
  if (property.datatype === 'integer' || property.datatype === 'decimal') return true;
  return (aggregate === 'min' || aggregate === 'max') && (property.datatype === 'date' || property.datatype === 'dateTime');
}

export function validateMetric(subject: Element | undefined, metric: Metric, properties: Property[]): FormErrors {
  const errors: FormErrors = {};
  if (subject?.kind !== 'entity_type' || subject.status !== 'active') errors.subjectRef = 'ontologyMetric.chooseSubject';
  if (metric.aggregate !== 'count' && metric.aggregate !== 'ratio' &&
      !properties.some((p) => p.propertyId === metric.propertyId && acceptsProperty(metric.aggregate, p))) {
    errors.propertyId = 'ontologyMetric.chooseProperty';
  }
  for (const key of ['filters', 'numerator'] as const) {
    if (key === 'numerator' && metric.aggregate !== 'ratio') continue;
    if (metric[key].some((f) => !properties.some((p) => p.propertyId === f.propertyId && p.ops.includes(f.op)))) {
      errors[key] = 'ontologyMetric.replaceCondition';
    }
  }
  if (metric.aggregate === 'ratio' && !metric.numerator.length) errors.numerator = 'ontologyMetric.needNumerator';
  return errors;
}

interface MetricEditorProps {
  metric: Metric;
  properties: Property[];
  onChange: (metric: Metric) => void;
  fieldId: (key: string) => string;
  onTouch: (key: string) => void;
  errorFor: (key: string) => string | undefined;
  onFiltersOpen: (open: boolean) => void;
  onNumeratorOpen: (open: boolean) => void;
}

export function MetricEditor({ metric, properties, onChange, fieldId, onTouch, errorFor, onFiltersOpen, onNumeratorOpen }: MetricEditorProps) {
  const { t } = useTranslation();
  const ratio = metric.aggregate === 'ratio';
  const needsProperty = !ratio && metric.aggregate !== 'count';
  const eligible = properties.filter((p) => acceptsProperty(metric.aggregate, p));
  const propertyError = errorFor('propertyId');
  const conditionGroup = (key: 'filters' | 'numerator') => {
    const error = errorFor(key);
    return (
      <fieldset id={fieldId(key)} tabIndex={-1} aria-describedby={error ? fieldId(key + '-error') : undefined} className="min-w-0 space-y-2">
        <legend className="text-sm font-medium">{t(`ontologyMetric.${key}`)}{key === 'numerator' && <span className="ml-1 text-error-strong" aria-hidden>*</span>}</legend>
        <FilterEditor properties={properties} filters={metric[key]} onChange={(filters) => onChange({ ...metric, [key]: filters })}
          onExpandedChange={key === 'filters' ? onFiltersOpen : onNumeratorOpen} />
        {error && <p id={fieldId(key + '-error')} className="text-sm text-error-strong">{error}</p>}
      </fieldset>
    );
  };
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={fieldId('aggregate')} required>{t('ontologyMetric.aggregate')}</Label>
          <NativeSelect id={fieldId('aggregate')} value={metric.aggregate} required onChange={(event) => {
            const aggregate = aggregates.find((item) => item === event.target.value);
            if (aggregate) onChange({ ...metric, aggregate });
          }}>
            {aggregates.map((value) => <option key={value} value={value}>{t(`ontologyMetric.aggregates.${value}`)}</option>)}
          </NativeSelect>
        </div>
        {needsProperty && <div className="space-y-2">
          <Label htmlFor={fieldId('propertyId')} required>{t('ontologyMetric.property')}</Label>
          <NativeSelect id={fieldId('propertyId')} required value={eligible.find((p) => p.propertyId === metric.propertyId)?.propertyId ?? ''}
            aria-invalid={!!propertyError} aria-describedby={propertyError ? fieldId('propertyId-error') : undefined}
            onBlur={() => onTouch('propertyId')} onChange={(event) => onChange({ ...metric, propertyId: event.target.value || null })}>
            <option value="">{t('ontologyMetric.chooseProperty')}</option>
            {eligible.map((p) => <option key={p.propertyId} value={p.propertyId}>{p.label}</option>)}
          </NativeSelect>
          {propertyError && <p id={fieldId('propertyId-error')} className="text-sm text-error-strong">{propertyError}</p>}
        </div>}
      </div>
      {conditionGroup('filters')}
      {ratio && conditionGroup('numerator')}
      <div className="flex flex-wrap items-center gap-4">
        <div className="space-y-2">
          <Label htmlFor={fieldId('decimals')}>{t('ontologyMetric.decimals')}</Label>
          <NativeSelect id={fieldId('decimals')} value={metric.decimals} onChange={(event) => onChange({ ...metric, decimals: Number(event.target.value) })}>
            {[0, 1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </NativeSelect>
        </div>
        {ratio && <label className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" checked={metric.percent}
            onChange={(event) => onChange({ ...metric, percent: event.target.checked })} />
          {t('ontologyMetric.percent')}
        </label>}
      </div>
    </div>
  );
}

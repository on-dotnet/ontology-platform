import { useTranslation } from 'react-i18next';

import { MetricDefinition } from '@/features/ontology/metric-definition';

import type { ChangeItem } from './api';
import { effectiveFields, refLabel, shownFields, type RefContext } from './item-fields';

export function MetricItem({ item, context, merged }: { item: ChangeItem; context: RefContext; merged: boolean }) {
  const { t } = useTranslation();
  const nameOf = (ref: string) => refLabel(ref, context);
  const patch = effectiveFields(item);
  const hasDefinitionFields = 'metric' in patch || 'subjectRef' in patch || 'unit' in patch;
  if (merged) {
    const names = (['labelZh', 'labelEn', 'definitionZh', 'definitionEn'] as const).filter((key) => key in patch);
    if (!names.length && !hasDefinitionFields) return null;
    return (
      <section aria-label={t('reviewMetric.proposal')} className="mt-2 space-y-2">
        <h4 className="text-xs font-semibold text-muted-foreground">{t('reviewMetric.proposal')}</h4>
        {names.length > 0 && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {names.map((key) => (
              <div key={key} className="contents">
                <dt className="text-muted-foreground">{t(`review.fields.${key}`)}</dt>
                <dd className="min-w-0 break-words">{patch[key] || t('review.emptyValue')}</dd>
              </div>
            ))}
          </dl>
        )}
        {hasDefinitionFields && <MetricDefinition fields={patch} nameOf={nameOf} onlyPresent />}
      </section>
    );
  }
  const fields = shownFields(item);
  const compare = (item.op === 'update' || item.op === 'restore') && hasDefinitionFields;
  return (
    <div className="mt-2 space-y-2">
      {(fields.definitionZh || fields.definitionEn) && <p className="text-sm text-muted-foreground">{fields.definitionZh || fields.definitionEn}</p>}
      {compare && item.before ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {[{ label: 'reviewMetric.before', value: item.before }, { label: 'reviewMetric.after', value: fields }].map(({ label, value }) => (
            <section key={label} aria-label={t(label)} className="space-y-2 rounded-lg border border-border p-3">
              <h4 className="text-xs font-semibold text-muted-foreground">{t(label)}</h4>
              <MetricDefinition fields={value} nameOf={nameOf} />
            </section>
          ))}
        </div>
      ) : <MetricDefinition fields={fields} nameOf={nameOf} />}
    </div>
  );
}

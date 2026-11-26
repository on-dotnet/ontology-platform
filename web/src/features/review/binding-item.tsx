import { Database } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Badge } from '@/components/ui/badge';
import type { components } from '@/api/schema';
import type { ElementKind } from '@/features/ontologies/api';

import type { ChangeItem, ElementFields } from './api';
import { effectiveFields, refLabel, shownFields, type RefContext } from './item-fields';

type Evidence = ChangeItem['evidence'][number];
export type BindingValue = NonNullable<ElementFields['binding']>;
type CatalogFact = components['schemas']['CatalogEvidenceSource']['fact'];

export const BINDING_KINDS = ['type_binding', 'property_binding', 'relation_binding'] as const satisfies readonly ElementKind[];

export function isBindingKind(kind: ElementKind): boolean {
  return (BINDING_KINDS as readonly ElementKind[]).includes(kind);
}

/** What a binding points to: "表 mes.heat（主键 heat_no）", "列 weight_t", "外键（在起点表）cast_no → cast_no". */
export function bindingTarget(t: TFunction, binding: BindingValue | null | undefined): string {
  if (!binding) return '';
  const list = (values: readonly string[]) => values.join(t('common.listSeparator'));
  switch (binding.target) {
    case 'table':
      return t('review.binding.table', { table: `${binding.schema}.${binding.table}`, keys: list(binding.keyColumns) });
    case 'column':
      return t('review.binding.column', { column: binding.column });
    case 'join': {
      const { join } = binding;
      // The side and the link columns are part of the sentence: an update may change only them.
      return join.kind === 'foreign_key'
        ? t(join.side === 'source' ? 'review.binding.foreignKeySource' : 'review.binding.foreignKeyTarget', {
            columns: list(join.columns),
            references: list(join.references),
          })
        : t('review.binding.linkTable', {
            table: `${join.schema}.${join.table}`,
            source: list(join.sourceColumns),
            target: list(join.targetColumns),
          });
    }
  }
}

/** One sentence for a binding item, e.g. "炉次 → 表 mes.heat（主键 heat_no）" or "属性 重量 → 列 weight_t". */
export function bindingSentence(t: TFunction, item: ChangeItem, context: RefContext): string {
  const fields = shownFields(item);
  const subject = refLabel(fields.subjectRef, context) ?? t('review.unknownElement');
  const kind = item.kind === 'type_binding' ? 'type' : item.kind === 'property_binding' ? 'property' : 'relation';
  return t(`review.binding.${kind}`, { subject, target: bindingTarget(t, fields.binding) });
}

/** The type binding this item hangs under, when it is proposed in the same change set and was rejected. */
function rejectedDependency(item: ChangeItem, context: RefContext): ChangeItem | undefined {
  if (item.op !== 'create' && item.op !== 'restore') return undefined;
  const fields = effectiveFields(item);
  const refs = item.kind === 'property_binding' ? [fields.parentRef] : item.kind === 'relation_binding' ? [fields.domainRef, fields.rangeRef] : [];
  return refs
    .map((ref) => (ref ? context.itemsByTempRef.get(ref) : undefined))
    .find((dependency) => dependency?.kind === 'type_binding' && dependency.decision === 'rejected');
}

/** Notices on a binding item: a key no constraint confirms, and a table binding the reviewer turned down. */
export function BindingNotices({ item, context }: { item: ChangeItem; context: RefContext }) {
  const { t } = useTranslation();
  const keyUnverified = item.flags.includes('key_unverified');
  const dependency = rejectedDependency(item, context);
  if (!keyUnverified && !dependency) return null;
  return (
    <div className="mt-2 space-y-2">
      {keyUnverified ? (
        <InlineNotice tone="warning" title={t('review.binding.keyUnverified.title')} announce={false}>
          {t('review.binding.keyUnverified.description')}
        </InlineNotice>
      ) : null}
      {dependency ? (
        <InlineNotice tone="info" title={t('review.binding.dependencyRejected')} announce={false}>
          {bindingSentence(t, dependency, context)}
        </InlineNotice>
      ) : null}
    </div>
  );
}

/** Before → after of an updated binding. */
export function BindingComparison({ item }: { item: ChangeItem }) {
  const { t } = useTranslation();
  const before = bindingTarget(t, item.before?.binding);
  const after = bindingTarget(t, effectiveFields(item).binding);
  if (!after || before === after) return null;
  return (
    <dl className="mt-2 rounded-lg border border-border bg-background p-3 text-sm">
      <div className="grid gap-1 sm:grid-cols-[6rem_1fr]">
        <dt className="text-xs font-medium text-muted-foreground">{t('review.binding.field')}</dt>
        <dd className="min-w-0 space-y-0.5">
          <p className="text-muted-foreground line-through">
            <span className="sr-only">{t('review.before')}</span>
            {before || t('review.emptyValue')}
          </p>
          <p className="text-foreground">
            <span className="sr-only">{t('review.after')}</span>
            {after}
          </p>
        </dd>
      </div>
    </dl>
  );
}

const FACT_ORDER: readonly CatalogFact[] = ['table', 'primary_key', 'column', 'foreign_key', 'sample'];

/** Catalog evidence: the facts of the data source's catalog a binding rests on, not a document excerpt. */
export function CatalogEvidenceList({ evidence }: { evidence: readonly Evidence[] }) {
  const { t } = useTranslation();
  const facts = [...evidence].sort(
    (a, b) => FACT_ORDER.indexOf(a.source?.fact ?? 'table') - FACT_ORDER.indexOf(b.source?.fact ?? 'table'),
  );
  return (
    <ul className="space-y-2" aria-label={t('review.catalogEvidence.label')}>
      {facts.map((entry) => {
        const source = entry.source;
        const place = source ? [source.schema, source.table, source.column].filter(Boolean).join('.') : '';
        return (
          <li key={entry.id} className="space-y-1 rounded-lg border border-border bg-background p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="neutral">
                <Database aria-hidden />
                {t(`review.catalogEvidence.facts.${source?.fact ?? 'table'}`)}
              </Badge>
              {place ? <span className="min-w-0 break-all font-mono text-xs text-muted-foreground">{place}</span> : null}
            </div>
            <p className="break-words font-mono text-xs text-foreground">{entry.quote}</p>
          </li>
        );
      })}
    </ul>
  );
}
